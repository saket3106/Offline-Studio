import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import app
from PySide6.QtWidgets import QApplication
from integrated_runtime import EngineManager


# Ensure QApplication exists for Qt widgets
_app = QApplication.instance() or QApplication([])


class TestChatModelSelection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "offline_gpt.sqlite3"

    def tearDown(self):
        try:
            self.tmp.cleanup()
        except Exception:
            pass

    def test_store_migrates_model_override_and_stores_per_chat(self):
        with patch.object(app, "DB_PATH", self.db_path), patch.object(app, "DATA_DIR", self.root):
            store = app.Store()
            try:
                # 1. Check table info has model_override
                cols = [r[1] for r in store.con.execute("PRAGMA table_info(chats)").fetchall()]
                self.assertIn("model_override", cols)

                # 2. new_chat without override
                cid1 = store.new_chat("Chat Default")
                self.assertEqual(store.get_chat_model(cid1), "")

                # 3. new_chat with override
                cid2 = store.new_chat("Chat Custom", model_override="qwen3-8b-custom")
                self.assertEqual(store.get_chat_model(cid2), "qwen3-8b-custom")

                # 4. set_chat_model
                store.set_chat_model(cid1, "gpt-oss-alt")
                self.assertEqual(store.get_chat_model(cid1), "gpt-oss-alt")

                # 5. chats_with_updated
                rows = store.chats_with_updated()
                chat_map = {r[0]: (r[1], r[3]) for r in rows}
                self.assertEqual(chat_map[cid1], ("Chat Default", "gpt-oss-alt"))
                self.assertEqual(chat_map[cid2], ("Chat Custom", "qwen3-8b-custom"))

                # 6. export_records includes model
                records = store.export_records([cid1, cid2])
                rec_map = {r["id"]: r.get("model") for r in records}
                self.assertEqual(rec_map[cid1], "gpt-oss-alt")
                self.assertEqual(rec_map[cid2], "qwen3-8b-custom")
            finally:
                store.con.close()

    def test_legacy_chats_table_without_column_is_safely_migrated(self):
        # Create legacy database with 3-column chats table
        with sqlite3.connect(self.db_path) as con:
            con.execute("CREATE TABLE chats(id TEXT PRIMARY KEY, title TEXT, updated REAL)")
            con.execute("INSERT INTO chats VALUES('legacy-1', 'Old Conversation', 1000.0)")
            con.commit()

        with patch.object(app, "DB_PATH", self.db_path), patch.object(app, "DATA_DIR", self.root):
            store = app.Store()
            try:
                # Existing legacy record should have empty model_override
                self.assertEqual(store.get_chat_model("legacy-1"), "")

                # Can set override on legacy chat
                store.set_chat_model("legacy-1", "upgraded-model")
                self.assertEqual(store.get_chat_model("legacy-1"), "upgraded-model")
            finally:
                store.con.close()

    def test_desktop_bridge_chat_model_slots(self):
        with patch.object(app, "DB_PATH", self.db_path), patch.object(app, "DATA_DIR", self.root):
            store = app.Store()
            try:
                backend = Mock()
                backend.store = store
                backend.current = ""
                backend.attachment = ""
                backend.busy = False
                backend.voice_mode_active = False
                backend.title = Mock()
                backend.cancel_voice_input = Mock()

                bridge = app.DesktopBridge(backend, None)

                # Test newChatWithModel
                cid = bridge.newChatWithModel("model-x")
                self.assertTrue(cid)
                self.assertEqual(backend.current, cid)
                self.assertEqual(store.get_chat_model(cid), "model-x")

                # Test getChatModel
                self.assertEqual(bridge.getChatModel(cid), "model-x")

                # Test setChatModel
                res_raw = bridge.setChatModel(cid, "model-y")
                res = json.loads(res_raw)
                self.assertTrue(res.get("ok"))
                self.assertEqual(bridge.getChatModel(cid), "model-y")

                # Test getChats includes model field
                chats_json = json.loads(bridge.getChats())
                matched = [c for c in chats_json if c["id"] == cid]
                self.assertEqual(len(matched), 1)
                self.assertEqual(matched[0]["model"], "model-y")
            finally:
                store.con.close()

    def test_engine_manager_resolve_model_path(self):
        dummy_model = self.root / "test_model.gguf"
        dummy_model.write_bytes(b"gguf-data")
        default_model = self.root / "default_model.gguf"
        default_model.write_bytes(b"default-data")

        cfg = {"gpt_oss_gguf": str(default_model), "chat_backend": "bundled"}
        manager = EngineManager()
        manager.cfg = cfg
        manager.log_dir = self.root / "logs"

        # 1. Empty / default resolves to default_model
        self.assertEqual(manager.resolve_model_path(""), default_model)
        self.assertEqual(manager.resolve_model_path("default"), default_model)
        self.assertEqual(manager.resolve_model_path(None), default_model)

        # 2. Direct file path resolves
        self.assertEqual(manager.resolve_model_path(str(dummy_model)), dummy_model)

        # 3. Model reference in database
        with sqlite3.connect(self.root / "offline_gpt.sqlite3") as con:
            con.execute(
                "CREATE TABLE local_model_references(id TEXT PRIMARY KEY, path TEXT COLLATE NOCASE UNIQUE NOT NULL, observation TEXT, details TEXT, created REAL)"
            )
            con.execute(
                "INSERT INTO local_model_references VALUES('ref-123', ?, '{}', '{}', 1.0)",
                (str(dummy_model),),
            )
            con.commit()

        # Resolve via reference ID
        resolved = manager.resolve_model_path("ref-123")
        self.assertEqual(resolved, dummy_model)

        # 4. Resolve via configured chat_model display name
        manager.cfg["chat_model"] = "Qwen3 4B Instruct · GGUF Q4_K_M"
        self.assertEqual(manager.resolve_model_path("Qwen3 4B Instruct · GGUF Q4_K_M"), default_model)

        # 5. Resolve via filename
        self.assertEqual(manager.resolve_model_path("test_model.gguf"), dummy_model)
        self.assertEqual(manager.resolve_model_path("default_model.gguf"), default_model)

        # 6. Resolve via model display name in local_model_references details
        with sqlite3.connect(self.root / "offline_gpt.sqlite3") as con:
            con.execute(
                "UPDATE local_model_references SET details=? WHERE id='ref-123'",
                (json.dumps({"name": "Test Qwen Model"}),),
            )
            con.commit()
        self.assertEqual(manager.resolve_model_path("Test Qwen Model"), dummy_model)

        # 7. Unknown model target raises RuntimeError
        with self.assertRaises(RuntimeError):
            manager.resolve_model_path("non_existent_model_id")

    def test_runtime_display_does_not_replace_selected_default(self):
        from types import SimpleNamespace
        backend=SimpleNamespace(model="configured-selection")
        with patch.object(app,"ROUTER_MODEL","configured-selection"):
            app.App.model_ready(backend,"Qwen3 4B Instruct · GGUF Q4_K_M")
            self.assertEqual(backend.model,"configured-selection")
            self.assertEqual(app.ROUTER_MODEL,"configured-selection")
            self.assertIn("GGUF",backend.model_display)

    def test_main_chat_worker_preserves_fresh_profile_model_identity(self):
        # A real ChatWorker must not resolve the inspected label as a new selection.
        from types import SimpleNamespace
        from intelligence import analyze_request,build_system_prompt
        model=self.root/"qwen.gguf";model.write_bytes(b"fixture")
        manager=EngineManager();manager.cfg={"gpt_oss_gguf":str(model),"chat_model":"Qwen3 4B Instruct"};manager.log_dir=self.root/"logs"
        calls=[]
        class Engine:
            runtime=SimpleNamespace(last_generation_diagnostics={})
            def ensure_chat(self,progress,selection,cancel_event):
                self.selection=selection
                assert manager.resolve_model_path(selection)==model
                return "Qwen3 4B Instruct · GGUF Q4_K_M"
            def chat_completion(self,messages,**kw):
                calls.append(kw["model"])
                assert manager.resolve_model_path(kw["model"])==model
                text="The atmosphere scatters blue light more strongly than red light."
                kw["on_token"](text);return text
        prompt="Explain in one sentence why the sky looks blue."
        analysis=analyze_request(prompt);engine=Engine()
        worker=app.ChatWorker(manager.cfg["chat_model"],[{"role":"system","content":build_system_prompt("",analysis)},{"role":"user","content":prompt}],engine,analysis)
        answers,errors,labels=[],[],[]
        worker.done.connect(answers.append);worker.failed.connect(errors.append);worker.modelReady.connect(labels.append)
        worker.run()
        self.assertEqual(errors,[]);self.assertTrue(answers)
        self.assertTrue(calls);self.assertEqual(set(calls),{"Qwen3 4B Instruct"})
        self.assertEqual(labels,["Qwen3 4B Instruct · GGUF Q4_K_M"])
        # Metadata remains ineligible as an implicit arbitrary-model fallback.
        with self.assertRaises(RuntimeError):manager.resolve_model_path(labels[0])

    def test_all_model_preparation_workers_keep_identity_separate(self):
        import ast
        tree=ast.parse(Path(app.__file__).read_text(encoding="utf-8"))
        assignments=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Assign) and isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Attribute) and node.value.func.attr=="ensure_chat":
                assignments.extend(ast.unparse(t) for t in node.targets)
        self.assertEqual(assignments.count("self.model_display"),4)
        self.assertNotIn("self.model",assignments)

    def test_fit_messages_preserves_fitting_prompt_when_target_output_unreduced(self):
        from integrated_runtime import _LocalLlamaServer
        server = _LocalLlamaServer(self.root / "logs")
        server.context = 2048
        server._prompt_tokens = lambda msgs: 850

        # Prompt with 850 tokens fits in 2048 with 128 answer tokens reserved,
        # even though 850 > 2048 - 1200 - 16 = 832.
        messages = [{"role": "user", "content": "hello world"}]
        fitted, prompt_tokens, output_tokens, shortened = server._fit_messages(messages, max_tokens=1200, progress=lambda _: None, cancel_event=None)
        self.assertGreaterEqual(output_tokens, 128)
        self.assertLessEqual(prompt_tokens + output_tokens, server.context)


    def test_store_reuse_empty_chat_and_cleanup_trash(self):
        with patch.object(app, "DB_PATH", self.db_path), patch.object(app, "DATA_DIR", self.root):
            store = app.Store()
            # 1. First new_chat creates an id
            cid1 = store.new_chat("New chat", reuse_empty=True)
            self.assertTrue(cid1)

            # 2. Second new_chat with reuse_empty=True should return the SAME id because it has 0 messages
            cid2 = store.new_chat("New chat", reuse_empty=True)
            self.assertEqual(cid1, cid2)

            # 3. If we add a message to cid1, then new_chat(reuse_empty=True) must create a brand NEW id
            store.add(cid1, "user", "Hello world")
            cid3 = store.new_chat("New chat", reuse_empty=True)
            self.assertNotEqual(cid1, cid3)

            # 4. If we soft-delete an empty chat into chat_trash, cleanup_empty_trash removes it
            empty_del = store.new_chat("Empty to delete")
            store.trash_chats([empty_del])
            trash_before = store.trash()
            self.assertTrue(any(t[0] == empty_del for t in trash_before))
            store.cleanup_empty_trash()
            trash_after = store.trash()
            self.assertFalse(any(t[0] == empty_del for t in trash_after))


if __name__ == "__main__":
    unittest.main()
