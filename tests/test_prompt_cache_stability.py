"""Turn 2 of every chat re-read the whole conversation (real app 2026-11-13: 0 tokens reused, ~1 s first token):
the identity lines said "pending load" on turn 1 and "loaded" on turn 2, and the 128 MB host prompt cache could not
hold a Qwen3.5 conversation state (~230 MB) across the chat-title request."""
import unittest
from pathlib import Path

from integrated_runtime import _local_memory_profile
from intelligence import _runtime_identity_section

GIB = 1024 ** 3
SOURCE = Path(__file__).resolve().parents[1]


def profile(available_gib, hw='balanced'):
    return _local_memory_profile({'total': 16 * GIB, 'available': int(available_gib * GIB), 'pagefile_available': 40 * GIB},
                                 4096, hardware_profile=hw)


class PromptCacheStabilityTests(unittest.TestCase):
    def test_identity_does_not_change_when_the_model_finishes_loading(self):
        selected = {'displayName': 'Qwen3.5 9B', 'modelPath': r'Models\Chat\Qwen3.5-9B-Q4_K_M.gguf', 'backend': 'bundled'}
        before = _runtime_identity_section(dict(selected, loaded=False))
        after = _runtime_identity_section(dict(selected, loaded=True))
        self.assertEqual(before, after)
        self.assertIn('Qwen3.5 9B', after)
        self.assertNotIn('pending load', after)

    def test_loaded_runtime_reports_the_selected_name_and_path_for_the_same_file(self):
        text = (SOURCE / 'integrated_runtime.py').read_text(encoding='utf-8')
        start = text.index('    def chat_identity_context(self, model_path=None):')
        body = text[start:start + 4000]
        self.assertIn('display = status.get("modelName") or display', body)
        self.assertIn('path = status.get("modelPath")', body)

    def test_host_prompt_cache_holds_a_conversation_when_ram_allows(self):
        self.assertEqual(profile(8)['cache_ram_mb'], 1024)
        self.assertEqual(profile(4.5)['cache_ram_mb'], 512)
        self.assertEqual(profile(2)['cache_ram_mb'], 256)
        self.assertEqual(profile(12, 'performance')['cache_ram_mb'], 2048)
        self.assertEqual(profile(12, 'eco')['cache_ram_mb'], 256)
        text = (SOURCE / 'integrated_runtime.py').read_text(encoding='utf-8')
        self.assertIn("cache_ram=max(0,min(4096,int((memory_profile or {}).get('cache_ram_mb',128))))", text)


if __name__ == '__main__':
    unittest.main()
