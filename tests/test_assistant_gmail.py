"""Email without a mail password: the draft opens in Gmail in Chrome, now or at the scheduled time (owner request 2026-11-09)."""
import os, sys, tempfile, time, unittest
from urllib.parse import urlparse, parse_qs
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import assistant_actions as aa
from assistant_host import AssistantHost


class GmailTests(unittest.TestCase):
    def make(self, cfg):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.events, self.opened, self.sent = [], [], []
        return AssistantHost(self.tmp.name, lambda: cfg, self.events.append, app_index=aa.AppIndex(providers=[lambda: []]),
                             sender=lambda c, p, m: self.sent.append(m["To"]), browser=lambda url: self.opened.append(url) or "Chrome",
                             draft_fn=lambda req, name: {"subject": "Leave request", "body": "Hi,\n\nI need Friday off.\n\nSaket"})

    def card(self, host, text):
        card = host.plan(text)
        for _ in range(200):
            if host.card(card["id"])["status"] == "awaiting": return host.card(card["id"])
            time.sleep(0.01)
        self.fail(host.card(card["id"]))

    def test_compose_url_is_gmail_with_fields(self):
        q = parse_qs(urlparse(aa.gmail_compose_url("a@b.com", "Hi & bye", "Line 1\nLine 2")).query)
        self.assertEqual((q["view"][0], q["to"][0], q["su"][0], q["body"][0]), ("cm", "a@b.com", "Hi & bye", "Line 1\nLine 2"))

    def test_unconfigured_email_opens_gmail_now(self):
        host = self.make({}); card = self.card(host, "email boss@example.com asking for leave on Friday")
        result = host.execute(card["id"], {})
        self.assertTrue(result["ok"]); self.assertEqual(result["card"]["status"], "done"); self.assertEqual(self.sent, [])
        self.assertIn("mail.google.com/mail/?view=cm", self.opened[0]); self.assertIn("boss%40example.com", self.opened[0])

    def test_scheduled_gmail_draft_opens_when_due(self):
        host = self.make({}); card = self.card(host, "email boss@example.com asking for leave on Friday")
        result = host.execute(card["id"], {"sendAt": time.time() + 3600, "via": "gmail"})
        self.assertEqual(result["card"]["status"], "scheduled"); self.assertEqual(self.opened, [])
        items = host.outbox.list(); self.assertEqual(items[0]["via"], "gmail")
        host.outbox._save([dict(items[0], sendAt=time.time() - 1)]); host.poll_outbox()
        self.assertEqual(len(self.opened), 1); self.assertEqual(host.outbox.list()[0]["status"], "sent"); self.assertEqual(self.sent, [])

    def test_configured_account_still_sends_by_smtp_unless_gmail_chosen(self):
        cfg = {"assistant_email": "me@example.com", "assistant_smtp_host": "smtp.example.com"}
        host = self.make(cfg); host.mail_password = lambda: "pw"
        card = self.card(host, "email boss@example.com asking for leave on Friday")
        host.execute(card["id"], {}); self.assertEqual(self.sent, ["boss@example.com"]); self.assertEqual(self.opened, [])

    def test_bad_recipient_is_refused_before_opening(self):
        host = self.make({}); card = self.card(host, "email boss@example.com asking for leave on Friday")
        result = host.execute(card["id"], {"to": "not-an-address", "via": "gmail"})
        self.assertFalse(result["ok"]); self.assertEqual(self.opened, [])


if __name__ == "__main__":
    unittest.main()
