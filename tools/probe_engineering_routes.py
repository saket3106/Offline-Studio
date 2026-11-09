"""Bounded synthetic Responses tool round-trip using existing loopback credentials."""
import argparse
import http.client
import json
import os
import secrets
import socket
import tempfile
import threading
import time
import urllib.error
from pathlib import Path


ENDPOINT = 'http://localhost:20128/v1/responses'
MAX_RESPONSE_BYTES = 1024 * 1024


def request(payload, timeout):
    key = os.environ.get('OMNIROUTE_API_KEY')
    if not key:
        raise RuntimeError('Existing OMNIROUTE_API_KEY is unavailable')
    deadline = time.monotonic() + timeout
    connection = http.client.HTTPConnection('127.0.0.1', 20128, timeout=timeout)
    timer = None
    response = None
    try:
        connection.connect()
        transport = connection.sock

        def expire():
            try:
                transport.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            transport.close()

        timer = threading.Timer(max(0, deadline - time.monotonic()), expire)
        timer.daemon = True
        timer.start()
        connection.request('POST', '/v1/responses', body=json.dumps(payload).encode(),
                           headers={'Authorization': 'Bearer ' + key,
                                    'Content-Type': 'application/json'})
        response = connection.getresponse()
        if response.status != 200:
            raise urllib.error.HTTPError(ENDPOINT, response.status, 'Probe request rejected', None, None)
        body = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Probe deadline exceeded')
            transport.settimeout(remaining)
            chunk = response.read1(min(65536, MAX_RESPONSE_BYTES + 1 - len(body)))
            if not chunk:
                break
            body.extend(chunk)
            if len(body) > MAX_RESPONSE_BYTES:
                raise ValueError('Probe response exceeds size limit')
        return json.loads(body)
    finally:
        if timer is not None:
            timer.cancel()
        if response is not None:
            response.close()
        connection.close()


def save_results(path, results):
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix=path.name + '.', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(results, stream, indent=2)
            stream.write(chr(10))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def probe(model, timeout=40):
    started = time.monotonic()
    result = {'id': model, 'status': 'unverified', 'capabilities': [],
              'requests': 0, 'usage': [], 'endpoint': ENDPOINT}
    tools = [{'type': 'function', 'name': 'read_probe', 'description': 'Read the synthetic probe value.',
              'parameters': {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False}}]
    messages = [{'role': 'user', 'content': 'Call read_probe exactly once, then reply with only its value. No other actions.'}]
    payload = {'model': model, 'input': messages, 'tools': tools, 'store': False,
               'max_output_tokens': 512}
    try:
        result['requests'] += 1
        response = request(payload, timeout)
        result['usage'].append(response.get('usage'))
        result['returned_model'] = response.get('model')
        calls = [item for item in response.get('output', []) if item.get('type') == 'function_call']
        if len(calls) != 1 or calls[0].get('name') != 'read_probe' or json.loads(calls[0]['arguments']) != {}:
            result['status'] = 'tool_contract_failed'
            return result
        nonce = secrets.token_hex(12)
        payload['input'] = messages + response['output'] + [
            {'type': 'function_call_output', 'call_id': calls[0]['call_id'],
             'output': json.dumps({'value': nonce})}]
        payload['tool_choice'] = 'none'
        result['requests'] += 1
        response = request(payload, timeout)
        result['usage'].append(response.get('usage'))
        text = ''.join(part.get('text', '') for item in response.get('output', [])
                       for part in item.get('content', []) if part.get('type') == 'output_text')
        if response.get('status') == 'completed' and text.strip() == nonce:
            result.update(status='verified', capabilities=['synthetic_function_roundtrip'])
        else:
            result['status'] = 'observation_roundtrip_failed'
    except urllib.error.HTTPError as error:
        result.update(status='unavailable', http_status=error.code)
    except Exception as error:
        result.update(status='unavailable', error_type=type(error).__name__)
    finally:
        result['elapsed_seconds'] = round(time.monotonic() - started, 3)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('models', nargs='+')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=40)
    arguments = parser.parse_args()
    if not 1 <= len(arguments.models) <= 4 or not 1 <= arguments.timeout <= 60:
        parser.error('Use at most four routes and a 1-60 second request timeout')
    if arguments.output.exists():
        parser.error('Output already exists; preserve previous evidence')
    results = []
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    for model in dict.fromkeys(arguments.models):
        result = probe(model, arguments.timeout)
        results.append(result)
        save_results(arguments.output, results)
        print(json.dumps(result), flush=True)
    return 0 if any(result['status'] == 'verified' for result in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
