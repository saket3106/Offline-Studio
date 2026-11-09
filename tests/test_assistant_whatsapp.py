import tempfile
import time
import unittest
from pathlib import Path

import assistant_actions as aa
import pc_control
from assistant_host import AssistantHost


class WhatsAppIntentTests(unittest.TestCase):
    def test_common_phrasings(self):
        cases = {
            "Send a WhatsApp message to Mom saying I will be late tonight": ("Mom", "I will be late tonight"),
            "whatsapp Riya that I reached home": ("Riya", "I reached home"),
            "message John on WhatsApp saying see you at 6": ("John", "see you at 6"),
            "can you text my brother on whatsapp that the match starts at 8": ("brother", "the match starts at 8"),
            "WhatsApp +91 98765 43210: on my way": ("+91 98765 43210", "on my way"),
            "tell Priya on WhatsApp I am running 10 minutes late": ("Priya", "I am running 10 minutes late"),
            "send a whatsapp to mom": ("mom", ""),
        }
        for text, (to, body) in cases.items():
            intent = aa.detect(text)
            self.assertEqual((intent["kind"], intent["to"], intent["text"], intent["sendAt"]), ("whatsapp", to, body, None), text)

    def test_send_time_needs_scheduling_words(self):
        intent = aa.detect("send dad a whatsapp saying happy birthday, send it at 9 am")
        self.assertEqual(intent["text"], "happy birthday")
        self.assertIsNotNone(intent["sendAt"])

    def test_not_whatsapp(self):
        self.assertEqual(aa.detect("open whatsapp")["kind"], "launch")
        self.assertIsNone(aa.detect("how do I send a whatsapp message to someone"))
        self.assertEqual(aa.detect("write an email to boss@x.com about leave")["kind"], "email")

    def test_link(self):
        self.assertEqual(aa.whatsapp_url("+91 98765 43210", "hi & bye"), "whatsapp://send?phone=919876543210&text=hi%20%26%20bye")
        self.assertEqual(aa.whatsapp_url("Mom", "hi"), "whatsapp://send?text=hi")


class WhatsAppHostTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.opened = []; self.events = []
        self.host = AssistantHost(Path(self.tmp.name), lambda: {"assistant_enabled": True}, self.events.append,
                                  app_index=object(), power=object(), messenger=lambda phone, text: self.opened.append((phone, text)) or "WhatsApp")

    def test_nothing_opens_until_confirmed_then_contact_is_remembered(self):
        card = self.host.plan("whatsapp Mom that I will be late")
        self.assertEqual(card["status"], "awaiting"); self.assertEqual(self.opened, [])
        result = self.host.execute(card["id"], {"phone": "+91 98765 43210", "text": "Running late"})
        self.assertTrue(result["ok"]); self.assertEqual(self.opened, [("+91 98765 43210", "Running late")])
        again = self.host.plan("message mom on whatsapp saying home soon")
        self.assertEqual(again["phone"], "919876543210")

    def test_empty_message_is_refused(self):
        card = self.host.plan("send a whatsapp to mom")
        result = self.host.execute(card["id"], {})
        self.assertFalse(result["ok"]); self.assertEqual(result["card"]["status"], "awaiting"); self.assertEqual(self.opened, [])

    def test_scheduled_message_opens_when_due(self):
        card = self.host.plan("whatsapp Riya that hi")
        result = self.host.execute(card["id"], {"sendAt": time.time() + 3600})
        self.assertEqual(result["card"]["status"], "scheduled"); self.assertEqual(self.opened, [])
        item = self.host.outbox._load()[0]; item["sendAt"] = time.time() - 1; self.host.outbox._save([item])
        self.host.poll_outbox()
        self.assertEqual(self.opened, [("", "hi")])


class ReminderTests(unittest.TestCase):
    def test_reminders_become_timers(self):
        self.assertEqual(pc_control.quick_command("remind me in 10 minutes to check the oven"),
                         [{"tool": "timer", "args": {"minutes": 10.0, "label": "Reminder: Check the oven"}}])
        self.assertEqual(pc_control.quick_command("remind me to call mom in an hour")[0]["args"]["label"], "Reminder: Call mom")
        self.assertEqual(pc_control.quick_command("wake me up in 20 minutes")[0]["args"], {"minutes": 20.0, "label": "Reminder: Wake up"})
        self.assertIsNone(pc_control.quick_command("remind me what we discussed"))

    def test_clock_time_reminder(self):
        steps = pc_control.quick_command("set a reminder for 11:59 pm to join the call")
        self.assertEqual(steps[0]["args"]["label"], "Reminder: Join the call")
        self.assertGreater(steps[0]["args"]["minutes"], 0)


if __name__ == "__main__":
    unittest.main()
