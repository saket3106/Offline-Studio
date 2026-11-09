"""One-shot loopback ASR transport with bounded waiting and cancellation."""
import http.client
import socket
import threading
import time


def transcribe_request(port, body, content_type, cancel, timeout=120):
    """Never replay an inference POST, including after an ambiguous disconnect."""
    connection = http.client.HTTPConnection('127.0.0.1', int(port), timeout=timeout)
    done = threading.Event()
    outcome = {}

    def request():
        try:
            connection.connect()
            outcome['socket'] = connection.sock
            connection.request('POST', '/inference', body=body,
                               headers={'Content-Type': content_type})
            response = connection.getresponse()
            raw = response.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                raise RuntimeError('Whisper response exceeded the local response limit.')
            if response.status >= 400:
                raise RuntimeError(f'Whisper returned HTTP {response.status}: '
                                   + raw.decode('utf-8', 'replace')[-500:])
            outcome['text'] = raw.decode('utf-8', 'replace')
        except Exception as exc:
            outcome['error'] = exc
        finally:
            done.set()

    if cancel.is_set():
        raise InterruptedError('Local transcription cancelled.')
    thread = threading.Thread(target=request, name='whisper-loopback-request', daemon=True)
    deadline = time.monotonic() + timeout
    thread.start()
    try:
        while not done.wait(.025):
            if cancel.is_set():
                raise InterruptedError('Local transcription cancelled.')
            if time.monotonic() >= deadline:
                raise TimeoutError('Local transcription timed out. Retry a shorter recording or choose a faster voice backend.')
        if cancel.is_set():
            raise InterruptedError('Local transcription cancelled.')
        if 'error' in outcome:
            raise outcome['error']
        return outcome['text']
    finally:
        stream = outcome.get('socket') or connection.sock
        if stream:
            try:
                stream.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        connection.close()
        thread.join(.1)
