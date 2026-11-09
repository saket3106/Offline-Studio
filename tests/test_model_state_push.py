"""Every chat-model unload (idle keepalive, memory guard, voice/FLUX reservation)
notifies state listeners, so the status bar and Models page cannot drift apart."""
import unittest
from types import SimpleNamespace
from integrated_runtime import EngineManager


class UnloadNotifiesTests(unittest.TestCase):
    def manager(self):
        stopped = []
        fake = SimpleNamespace(last_unload_reason='', loaded_model='qwen.gguf', active_chat_backend='bundled', active_gpu_layers=99,
                               chat_memory_profile={}, chat_load_state='ready', state_listeners=[],
                               runtime=SimpleNamespace(stop=lambda graceful=True: stopped.append(graceful)),
                               lm_runtime=SimpleNamespace(unload=lambda stop_server=True: None), _cancel_idle_timer=lambda: None)
        return fake, stopped

    def test_listeners_receive_the_unload_reason(self):
        fake, stopped = self.manager(); seen = []
        fake.state_listeners.append(seen.append)
        EngineManager._unload_chat(fake, graceful=False, reason='Memory reserved for local microphone recognition')
        self.assertEqual(seen, ['Memory reserved for local microphone recognition'])
        self.assertEqual(fake.chat_load_state, 'unloaded'); self.assertEqual(fake.loaded_model, ''); self.assertEqual(stopped, [False])

    def test_failing_listener_never_blocks_the_unload(self):
        fake, _ = self.manager()
        fake.state_listeners.append(lambda reason: (_ for _ in ()).throw(RuntimeError('ui gone')))
        EngineManager._unload_chat(fake, reason='Keepalive expired')
        self.assertEqual(fake.chat_load_state, 'unloaded')


if __name__ == '__main__':
    unittest.main()
