import os, sys, tempfile, time, unittest
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import assistant_actions as aa
from assistant_host import AssistantHost, spoken_answer


class FakePower:
    def __init__(self): self.applied = []
    def preview(self, mode): return {"mode": mode, "target": {"guid": "g", "name": "High performance" if mode == "gaming" else "Balanced"}, "current": None, "gameMode": mode == "gaming"}
    def apply(self, preview): self.applied.append(preview["mode"]); return {"ok": True, "plan": preview["target"]["name"], "gameMode": preview["mode"] == "gaming"}


class FakeSecret:
    path = Path(__file__)
    def read(self): return "app-password"


class HostTests(unittest.TestCase):
    def make(self, cfg=None, draft=None):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.events, self.launched, self.sent = [], [], []
        apps = [{"name": "Grand Theft Auto V", "source": "steam", "target": "steam://rungameid/271590"}, {"name": "Notepad", "source": "windows", "target": "notepad.exe"}]
        cfg = cfg if cfg is not None else {"assistant_email": "me@example.com", "assistant_smtp_host": "smtp.example.com", "assistant_sender_name": "Saket"}
        self.power = FakePower()
        return AssistantHost(self.tmp.name, lambda: cfg, self.events.append, secret_store=FakeSecret(),
                             app_index=aa.AppIndex(providers=[lambda: apps]), power=self.power,
                             sender=lambda c, p, m: self.sent.append((p, m["To"], m["Subject"])),
                             launcher=lambda app: self.launched.append(app["target"]),
                             draft_fn=draft or (lambda req, name: {"subject": "Project update", "body": f"Hi,\n\nUpdate.\n\n{name}"}))

    def wait_for(self, host, cid, status):
        for _ in range(100):
            if host.card(cid)["status"] == status: return host.card(cid)
            time.sleep(0.01)
        self.fail(f"card never reached {status}: {host.card(cid)}")

    def test_play_gta_previews_then_launches_with_gaming_mode_only_after_confirm(self):
        host = self.make()
        card = host.plan("I'm feeling like playing GTA 5", source="voice")
        self.assertEqual(card["status"], "awaiting"); self.assertEqual(card["app"]["name"], "Grand Theft Auto V")
        self.assertIn("High performance", card["summary"])
        self.assertEqual(self.launched, []); self.assertEqual(self.power.applied, [])  # nothing happens before confirmation
        result = host.execute(card["id"])
        self.assertTrue(result["ok"]); self.assertEqual(self.launched, ["steam://rungameid/271590"]); self.assertEqual(self.power.applied, ["gaming"])
        self.assertFalse(host.execute(card["id"])["ok"])  # cannot run twice

    def test_unknown_app_falls_through_to_chat_instead_of_guessing(self):
        self.assertIsNone(self.make().plan("launch minecraft"))
        self.assertIsNone(self.make().plan("start a story about dragons"))

    def test_cancel(self):
        host = self.make(); card = host.plan("open notepad")
        host.cancel(card["id"]); self.assertFalse(host.execute(card["id"])["ok"]); self.assertEqual(self.launched, [])

    def test_email_to_several_people_is_ready_without_asking_for_an_address(self):
        host = self.make()
        card = host.plan("write an email to amit@example.com, priya@example.com and rahul@example.com about the Diwali offer")
        ready = self.wait_for(host, card["id"], "awaiting")
        self.assertEqual(ready["to"], "amit@example.com, priya@example.com, rahul@example.com")
        self.assertNotIn("Add the recipient", ready["summary"])
        self.assertIn("to 3 people", ready["spoken"])

    def test_email_is_drafted_by_model_then_sent_after_confirm(self):
        host = self.make()
        card = host.plan("write an email to sam@example.com about the project update")
        self.assertEqual(card["status"], "drafting")
        ready = self.wait_for(host, card["id"], "awaiting")
        self.assertEqual(ready["subject"], "Project update"); self.assertIn("Saket", ready["body"])
        self.assertEqual(self.sent, [])
        result = host.execute(card["id"], {"body": "Edited body"})
        self.assertTrue(result["ok"]); self.assertEqual(self.sent, [("app-password", "sam@example.com", "Project update")])

    def test_email_scheduled_goes_to_outbox_and_poll_sends_it(self):
        host = self.make()
        card = host.plan("send an email to sam@example.com about lunch and schedule it for tomorrow at 9 am")
        self.wait_for(host, card["id"], "scheduled"); self.assertEqual(self.sent, [])
        host.poll_outbox(); self.assertEqual(self.sent, [])
        items = host.outbox._load(); items[0]["sendAt"] = time.time() - 1; host.outbox._save(items)
        host.poll_outbox(); self.assertEqual(len(self.sent), 1); self.assertEqual(host.outbox.list()[0]["status"], "sent")

    def test_email_with_a_time_is_scheduled_without_a_click(self):
        host = self.make()
        card = host.plan("send an email to sam@example.com about lunch and schedule it for tomorrow at 9 am")
        self.wait_for(host, card["id"], "scheduled")
        self.assertEqual(self.sent, []); self.assertEqual(len(host.outbox.list()), 1)

    def test_email_without_recipient_stays_editable(self):
        host = self.make()
        card = host.plan("compose an email to my professor about the assignment")
        self.wait_for(host, card["id"], "awaiting")
        result = host.execute(card["id"])
        self.assertFalse(result["ok"]); self.assertEqual(result["card"]["status"], "awaiting"); self.assertIn("recipient", result["error"])
        self.assertTrue(host.execute(card["id"], {"to": "prof@uni.edu"})["ok"])

    def test_disabled_or_plain_chat_returns_none(self):
        self.assertIsNone(self.make({"assistant_actions_enabled": False}).plan("open notepad"))
        self.assertIsNone(self.make().plan("what is machine learning?"))

    def test_model_fallback_routes_phrasings_the_rules_miss(self):
        host = self.make()
        calls = []
        host.classify_fn = lambda text: calls.append(text) or {"action": "open_app", "target": "GTA V"}
        card = host.plan("I want GTA running, start it")
        self.assertEqual(card["app"]["name"], "Grand Theft Auto V"); self.assertEqual(len(calls), 1)
        host.classify_fn = lambda text: calls.append(text) or {"action": "none", "target": ""}
        for text in ["tell me a joke about cats", "write a poem about rain", "set up a study plan for me"]:
            self.assertIsNone(host.plan(text))  # no launch verb: the model is not even asked
        self.assertEqual(len(calls), 1)
        self.assertIsNone(host.plan("start with the basics of physics"))  # no installed app matches → ordinary chat
        self.assertIsNone(host.plan("please turn on the charm in your writing"))  # model says none → ordinary chat
        self.assertEqual(len(calls), 2)

    def test_spoken_answers(self):
        for t in ["Yes.", "yeah do it", "Okay", "send it"]: self.assertEqual(spoken_answer(t), "confirm", t)
        for t in ["No", "cancel that", "never mind"]: self.assertEqual(spoken_answer(t), "cancel", t)
        self.assertIsNone(spoken_answer("tell me a joke"))


if __name__ == "__main__":
    unittest.main()
