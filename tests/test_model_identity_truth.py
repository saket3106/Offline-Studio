"""Regression tests for truthful runtime model identity.

The recording showed Qwen3.5-9B selected while the reply claimed to be
GPT-OSS 20B.  These tests pin the application-verified identity path so a
model can never be attributed to a different installed model by prompt text.
"""
import unittest
from pathlib import Path

from intelligence import build_system_prompt, load_system_prompt
from integrated_runtime import EngineManager


QWEN35 = {
    "displayName": "Qwen3.5 9B",
    "selectedModel": "Qwen3.5 9B",
    "modelPath": r"C:\Models\Chat\Qwen3.5-9B-Q4_K_M.gguf",
    "backend": "bundled",
    "loaded": False,
    "loadState": "not-loaded",
    "identitySource": "untrusted_gguf_metadata",
}
QWEN4 = dict(QWEN35, displayName="Qwen3 4B", selectedModel="Qwen3 4B",
             modelPath=r"C:\Models\Chat\Qwen3-4B-Q4_K_M.gguf")
GPTOSS = dict(QWEN35, displayName="GPT-OSS 20B", selectedModel="GPT-OSS 20B",
              modelPath=r"C:\Models\Chat\gpt-oss-20b-MXFP4.gguf")


class TestRuntimeIdentityPrompt(unittest.TestCase):
    def _analysis(self):
        return {"category": "normal", "route_target": "DIRECT",
                "factual_grounding_state": "SUPPORTED", "constraints": {}}

    def test_shipped_prompt_has_no_fixed_model_identity(self):
        prompt = load_system_prompt(Path(__file__).resolve().parents[1])
        self.assertNotIn("GPT-OSS", prompt)
        self.assertNotIn("20B", prompt)
        self.assertIn("local model currently loaded", prompt)

    def test_identity_matches_qwen35_and_forbids_other_names(self):
        system = build_system_prompt("policy", self._analysis(), runtime_identity=QWEN35)
        self.assertIn("Qwen3.5 9B", system)
        self.assertIn("Qwen3.5-9B-Q4_K_M.gguf", system)
        self.assertIn("Never name a different model", system)
        self.assertNotIn("GPT-OSS 20B", system)

    def test_identity_changes_with_actual_model(self):
        a = build_system_prompt("policy", self._analysis(), runtime_identity=QWEN4)
        b = build_system_prompt("policy", self._analysis(), runtime_identity=GPTOSS)
        self.assertIn("Qwen3 4B", a)
        self.assertNotIn("GPT-OSS", a)
        self.assertIn("GPT-OSS 20B", b)
        self.assertNotIn("Qwen3 4B", b)

    def test_missing_selection_is_reported_not_invented(self):
        system = build_system_prompt("policy", self._analysis(),
                                     runtime_identity={"displayName": "", "loaded": False})
        self.assertIn("no local chat model is selected", system)
        self.assertNotIn("GPT-OSS", system)

    def test_identity_survives_condensed_and_rag_paths(self):
        compact = dict(self._analysis(), compact_conversation=True)
        self.assertIn("Qwen3.5 9B", build_system_prompt("policy", compact, runtime_identity=QWEN35))
        rag = dict(self._analysis(), route_target="DOCUMENT_RAG")
        text = build_system_prompt("policy", rag, rag_context="evidence", runtime_identity=QWEN35)
        self.assertIn("Qwen3.5 9B", text)

    def test_legacy_prompt_with_hardcoded_gpt_oss_is_sanitized(self):
        legacy = "You are Offline GPT, an intelligent, private local AI assistant running directly on the user's PC using local GPT-OSS 20B.\nDistinguish official GPT-OSS 20B architecture..."
        system = build_system_prompt(legacy, self._analysis(), runtime_identity=QWEN35)
        self.assertIn("Qwen3.5 9B", system)
        self.assertNotIn("GPT-OSS 20B", system)
        self.assertNotIn("official GPT-OSS 20B architecture", system)


class TestEngineIdentityContext(unittest.TestCase):
    def _manager(self, status):
        manager = EngineManager.__new__(EngineManager)
        manager.cfg = {"chat_backend": "bundled", "chat_model": "Qwen3.5-9B"}
        manager.chat_status = lambda: status
        return manager

    def test_loaded_runtime_wins_over_selection(self):
        manager = self._manager({
            "loaded": True, "runtimeLoaded": True, "modelName": "Qwen3.5 9B",
            "runtimeModelName": "Qwen3.5 9B", "runtimeModelPath": r"C:\m\qwen35.gguf",
            "modelPath": r"C:\m\qwen35.gguf", "backend": "bundled",
            "loadState": "ready", "modelIdentitySource": "untrusted_gguf_metadata",
            "engineName": "Bundled Offline GPT engine", "effectiveContext": 4096,
        })
        identity = manager.chat_identity_context()
        self.assertEqual(identity["displayName"], "Qwen3.5 9B")
        self.assertTrue(identity["loaded"])
        self.assertEqual(identity["backend"], "bundled")

    def test_unloaded_selection_is_not_reported_as_loaded(self):
        manager = self._manager({
            "loaded": False, "runtimeLoaded": False, "modelName": "Qwen3.5 9B",
            "runtimeModelName": "", "runtimeModelPath": "", "modelPath": r"C:\m\qwen35.gguf",
            "backend": "bundled", "loadState": "not-loaded",
            "modelIdentitySource": "untrusted_gguf_metadata", "effectiveContext": 4096,
        })
        identity = manager.chat_identity_context()
        self.assertFalse(identity["loaded"])
        self.assertEqual(identity["displayName"], "Qwen3.5 9B")
        self.assertEqual(identity["loadState"], "not-loaded")

    def test_status_failure_does_not_invent_a_model(self):
        manager = EngineManager.__new__(EngineManager)
        manager.cfg = {"chat_backend": "bundled"}
        manager.chat_status = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        identity = manager.chat_identity_context()
        self.assertEqual(identity["displayName"], "")
        self.assertFalse(identity["loaded"])


if __name__ == "__main__":
    unittest.main()
