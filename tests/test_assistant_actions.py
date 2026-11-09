import datetime as dt, json, os, sys, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import assistant_actions as aa


class Detect(unittest.TestCase):
    def test_play_requests_become_launch_with_gaming(self):
        for text, name in [("I'm feeling like playing GTA 5", "gta 5"), ("launch Valorant please", "valorant"),
                           ("let's play rdr2", "rdr2"), ("open notepad", "notepad"), ("fire up Counter-Strike 2 in gaming mode", "counter-strike 2")]:
            got = aa.detect(text)
            self.assertEqual(got["kind"], "launch", text); self.assertEqual(got["query"].lower(), name, text)
        self.assertTrue(aa.detect("I feel like playing GTA 5")["gaming"])
        self.assertFalse(aa.detect("open notepad")["gaming"])

    def test_store_names_are_not_part_of_the_app_name(self):
        # Real-app transcript: "Open GTA 5 from Epic Games" fell through to chat.
        for text in ["Open GTA 5 from Epic Games", "launch gta 5 on steam", "play GTA 5 from the Rockstar launcher"]:
            self.assertEqual(aa.detect(text)["query"].lower(), "gta 5", text)

    def test_music_requests(self):
        for text in ["play music", "Play some music please", "music", "put on some songs"]:
            got = aa.detect(text); self.assertEqual(got["kind"], "launch", text); self.assertTrue(got.get("music"), text)

    def test_power_modes(self):
        self.assertEqual(aa.detect("turn on extreme mode")["mode"], "gaming")
        self.assertEqual(aa.detect("switch to gaming mode")["mode"], "gaming")
        self.assertEqual(aa.detect("go back to balanced mode")["mode"], "normal")
        self.assertEqual(aa.detect("battery saver mode on")["mode"], "saver")

    def test_email(self):
        got = aa.detect("write an email to sam@example.com about the project deadline and schedule it for tomorrow at 9 am")
        self.assertEqual(got["kind"], "email"); self.assertEqual(got["to"], "sam@example.com")
        self.assertIn("project deadline", got["topic"]); self.assertIsNotNone(got["sendAt"])
        self.assertIsNone(aa.detect("send a mail to bob@x.org saying hi")["sendAt"])
        self.assertIsNotNone(aa.detect("email bob@x.org about lunch, send it in 10 minutes")["sendAt"])

    def test_email_to_several_people_keeps_every_address(self):
        got = aa.detect("Send a promotional offer email to amit@example.com, priya@example.com and rahul@example.com about our Diwali discount")
        self.assertEqual(got["to"], "amit@example.com, priya@example.com, rahul@example.com")
        self.assertEqual(got["topic"], "our Diwali discount")
        got = aa.detect("compose a mail to a@example.com; b@example.org; a@example.com regarding the offer and send it at 6 pm")
        self.assertEqual(got["to"], "a@example.com, b@example.org"); self.assertEqual(got["topic"], "the offer")
        self.assertIsNotNone(got["sendAt"])

    def test_times_inside_the_email_are_not_a_send_time(self):
        got = aa.detect("write an email to sam@example.com about moving tomorrow's team meeting to 3 pm")
        self.assertEqual(got["kind"], "email"); self.assertIsNone(got["sendAt"])

    def test_plain_chat_is_not_an_action(self):
        for text in ["what is machine learning?", "explain how games are made", "play a game with me", "can you start over",
                     "write a 500 word essay on gaming", "how does performance tuning work",
                     "how do I write an email to my professor?", "what should I say in a mail to HR",
                     "summarize this email thread for me", "tell me about gaming mode on Windows"]:
            self.assertIsNone(aa.detect(text), text)


class Resolve(unittest.TestCase):
    def setUp(self):
        apps = [{"name": "Grand Theft Auto V", "source": "steam", "target": "steam://rungameid/271590"},
                {"name": "Grand Theft Auto IV", "source": "steam", "target": "steam://rungameid/12210"},
                {"name": "Visual Studio Code", "source": "start menu", "target": "c.lnk"},
                {"name": "Notepad", "source": "windows", "target": "notepad.exe"},
                {"name": "VALORANT", "source": "start menu", "target": "v.lnk"}]
        self.index = aa.AppIndex(providers=[lambda: apps])

    def test_aliases_roman_numerals_and_acronyms(self):
        self.assertEqual(self.index.resolve("gta 5")[0]["name"], "Grand Theft Auto V")
        self.assertEqual(self.index.resolve("grand theft auto 5")[0]["name"], "Grand Theft Auto V")
        self.assertEqual(self.index.resolve("gta 4")[0]["name"], "Grand Theft Auto IV")
        self.assertEqual(self.index.resolve("vscode")[0]["name"], "Visual Studio Code")
        self.assertEqual(self.index.resolve("valorant")[0]["name"], "VALORANT")

    def test_unknown_app_resolves_to_nothing(self):
        self.assertEqual(self.index.resolve("minecraft"), [])

    def test_launch_uses_target_only(self):
        calls = []
        aa.launch_app(self.index.resolve("gta 5")[0], starter=calls.append)
        self.assertEqual(calls, ["steam://rungameid/271590"])


class Discovery(unittest.TestCase):
    def test_steam_and_epic_manifests(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "Steam"; (root / "steamapps").mkdir(parents=True)
            lib = Path(d) / "Lib2" / "steamapps"; lib.mkdir(parents=True)
            (root / "steamapps/libraryfolders.vdf").write_text('"libraryfolders" { "1" { "path" "%s" } }' % str(Path(d) / "Lib2").replace("\\", "\\\\"))
            (lib / "appmanifest_271590.acf").write_text('"AppState" { "appid" "271590" "name" "Grand Theft Auto V" }')
            (lib / "appmanifest_228980.acf").write_text('"AppState" { "appid" "228980" "name" "Steamworks Common Redistributables" }')
            self.assertEqual(aa.steam_games(root), [{"name": "Grand Theft Auto V", "source": "steam", "target": "steam://rungameid/271590"}])
            man = Path(d) / "Manifests"; man.mkdir()
            (man / "x.item").write_text(json.dumps({"DisplayName": "Fortnite", "CatalogNamespace": "fn", "CatalogItemId": "abc", "AppName": "Fortnite"}))
            self.assertIn("com.epicgames.launcher://apps/fn%3Aabc%3AFortnite", aa.epic_games(man)[0]["target"])

    def test_start_menu_skips_uninstallers(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "Game.lnk").write_text(""); (Path(d) / "Uninstall Game.lnk").write_text("")
            self.assertEqual([a["name"] for a in aa.start_menu_apps([Path(d)])], ["Game"])


POWERCFG_LIST = """Existing Power Schemes (* Active)
-----------------------------------
Power Scheme GUID: 381b4222-f694-41f0-9685-ff5bb260df2e  (Balanced) *
Power Scheme GUID: 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c  (High performance)
Power Scheme GUID: a1841308-3541-4fab-bc81-f71556f20b4a  (Power saver)
"""


class Power(unittest.TestCase):
    def runner(self, listing=POWERCFG_LIST):
        self.calls = []
        def run(cmd):
            self.calls.append(cmd[1:])
            if cmd[1] == "/list": return SimpleNamespace(returncode=0, stdout=listing, stderr="")
            if cmd[1] == "-duplicatescheme": return SimpleNamespace(returncode=0, stdout="Power Scheme GUID: 11111111-2222-3333-4444-555555555555  (High performance)", stderr="")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return run

    def test_gaming_then_back_to_previous(self):
        reg = SimpleNamespace(HKEY_CURRENT_USER=1, REG_DWORD=4, CreateKey=lambda *a: _Key(), SetValueEx=lambda *a: None)
        pc = aa.PowerController(runner=self.runner(), winreg_module=reg)
        preview = pc.preview("gaming")
        self.assertEqual(preview["target"]["name"], "High performance")
        result = pc.apply(preview)
        self.assertEqual(result["plan"], "High performance"); self.assertTrue(result["gameMode"])
        self.assertIn(["/setactive", aa.HIGH_PERFORMANCE], self.calls)
        back = pc.preview("normal"); self.assertEqual(back["target"]["guid"], aa.BALANCED)

    def test_creates_high_performance_when_missing(self):
        listing = POWERCFG_LIST.replace("Power Scheme GUID: 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c  (High performance)\n", "")
        pc = aa.PowerController(runner=self.runner(listing), winreg_module=None)
        preview = pc.preview("gaming"); self.assertTrue(preview["target"].get("create"))
        pc.apply(preview)
        self.assertIn(["/setactive", "11111111-2222-3333-4444-555555555555"], self.calls)


class _Key:
    def __enter__(self): return self
    def __exit__(self, *a): return False


class Email(unittest.TestCase):
    def test_build_validates_addresses(self):
        with self.assertRaises(ValueError): aa.build_message("me@x.com", "not-an-address", "s", "b")
        msg = aa.build_message("me@x.com", "a@y.com, b@z.org", "Hi", "Body")
        self.assertEqual(msg["To"], "a@y.com, b@z.org")

    def test_send_uses_starttls_and_login(self):
        log = []
        class FakeSMTP:
            def __enter__(s): return s
            def __exit__(s, *a): return False
            def ehlo(s): log.append("ehlo")
            def starttls(s, context=None): log.append("starttls")
            def login(s, u, p): log.append(("login", u, p))
            def send_message(s, m): log.append(("send", m["To"]))
        cfg = {"assistant_smtp_host": "smtp.example.com", "assistant_smtp_port": 587, "assistant_email": "me@example.com"}
        aa.send_email(cfg, "pw", aa.build_message("me@example.com", "a@y.com", "S", "B"), smtp_factory=FakeSMTP)
        self.assertEqual(log, ["ehlo", "starttls", "ehlo", ("login", "me@example.com", "pw"), ("send", "a@y.com")])

    def test_not_configured_is_a_clear_error(self):
        with self.assertRaisesRegex(RuntimeError, "Settings"):
            aa.send_email({}, "", aa.build_message("me@x.com", "a@y.com", "S", "B"))

    def test_presets(self):
        self.assertEqual(aa.smtp_preset("someone@gmail.com"), ("smtp.gmail.com", 587))

    def test_connect_signs_in_without_sending_and_explains_a_rejected_password(self):
        import smtplib
        log = []
        def factory(reject=False):
            class FakeSMTP:
                def __enter__(s): return s
                def __exit__(s, *a): return False
                def ehlo(s): log.append("ehlo")
                def starttls(s, context=None): log.append("starttls")
                def login(s, u, p):
                    if reject: raise smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted")
                    log.append(("login", u, p))
                def send_message(s, m): log.append("SENT")
            return FakeSMTP
        cfg = {"assistant_smtp_host": "smtp.gmail.com", "assistant_smtp_port": 587, "assistant_email": "me@gmail.com"}
        aa.verify_login(cfg, aa.clean_app_password("abcd efgh ijkl mnop"), smtp_factory=factory())
        self.assertIn(("login", "me@gmail.com", "abcdefghijklmnop"), log); self.assertNotIn("SENT", log)
        with self.assertRaisesRegex(ValueError, "App Password"):
            aa.verify_login(cfg, "wrong", smtp_factory=factory(reject=True))
        with self.assertRaisesRegex(ValueError, "Enter your email"):
            aa.verify_login({}, "x")

    def test_college_and_company_addresses_find_their_mail_server_from_mx(self):
        mx = {"students.example.edu": ["aspmx.l.google.com", "alt1.aspmx.l.google.com"],
              "corp.example": ["corp-example.mail.protection.outlook.com"], "odd.example": ["mx.odd.example"]}
        find = lambda a: aa.find_smtp(a, lookup=lambda d: mx.get(d, []))
        self.assertEqual(find("student@students.example.edu"), ("smtp.gmail.com", 587))
        self.assertEqual(find("a@corp.example"), ("smtp.office365.com", 587))
        self.assertIsNone(find("a@odd.example"))
        self.assertEqual(find(" Me@Gmail.com "), ("smtp.gmail.com", 587))

    def test_typed_mail_server_names_are_understood(self):
        self.assertEqual(aa.server_from_text("gmail"), ("smtp.gmail.com", 587))
        self.assertEqual(aa.server_from_text("Gmail.com"), ("smtp.gmail.com", 587))
        self.assertEqual(aa.server_from_text("https://smtp.gmail.com:465/"), ("smtp.gmail.com", 465))
        self.assertEqual(aa.server_from_text("microsoft"), ("smtp.office365.com", 587))
        self.assertEqual(aa.server_from_text("mail.college.edu"), ("mail.college.edu", 587))
        self.assertIsNone(aa.server_from_text("  "))

    def test_unreachable_server_is_named_in_the_error(self):
        def refuse(): raise ConnectionRefusedError("refused")
        with self.assertRaisesRegex(ValueError, "smtp.example.com"):
            aa.verify_login({"assistant_smtp_host": "smtp.example.com", "assistant_email": "a@example.com"}, "x", smtp_factory=refuse)

    def test_server_hanging_up_on_the_password_is_a_password_problem(self):
        import smtplib
        class Hangup:
            def __enter__(s): return s
            def __exit__(s, *a): return False
            def ehlo(s): pass
            def starttls(s, context=None): pass
            def login(s, u, p): raise smtplib.SMTPServerDisconnected("Connection unexpectedly closed")
        cfg = {"assistant_smtp_host": "smtp.gmail.com", "assistant_email": "me@gmail.com"}
        with self.assertRaisesRegex(ValueError, "App Password"):
            aa.verify_login(cfg, "normal-password", smtp_factory=Hangup)

    def test_plain_clock_time_outside_the_message_is_the_send_time(self):
        hit = aa.detect('mail dad@example.com this message-"Hello Dad" at 6:50am from my connected mail')
        self.assertIsNotNone(hit["sendAt"])
        self.assertIsNone(aa.detect('email a@b.com saying "meet me at 5pm"')["sendAt"])

    def test_signature_placeholder_is_filled_or_removed(self):
        body = "Dear Sir,\n\nThank you.\n\nBest regards,\n[Your Name]"
        self.assertTrue(aa.fill_signature(body, "Saket").endswith("Best regards,\nSaket"))
        self.assertTrue(aa.fill_signature(body, "").endswith("Best regards,"))
        self.assertNotIn("[", aa.fill_signature("Regards, [Name]", "A"))

    def test_outbox_schedule_due_cancel(self):
        with tempfile.TemporaryDirectory() as d:
            box = aa.Outbox(Path(d) / "outbox.json")
            a = box.add("a@y.com", "S", "B", 100); b = box.add("b@y.com", "S", "B", 200)
            self.assertEqual([i["id"] for i in box.due(150)], [a["id"]])
            self.assertEqual(box.due(150), [])  # not returned twice
            self.assertTrue(box.cancel(b["id"])); self.assertEqual(box.due(500), [])
            box.mark(a["id"], "sent"); self.assertEqual(box.list()[0]["status"], "sent")


class When(unittest.TestCase):
    now = dt.datetime(2026, 11, 7, 14, 0)  # Saturday 2 pm

    def test_relative_and_absolute(self):
        self.assertEqual(aa.parse_when("in 10 minutes", self.now), self.now + dt.timedelta(minutes=10))
        self.assertEqual(aa.parse_when("at 5 pm", self.now), dt.datetime(2026, 11, 7, 17, 0))
        self.assertEqual(aa.parse_when("at 9", self.now), dt.datetime(2026, 11, 8, 9, 0))
        self.assertEqual(aa.parse_when("tomorrow at 9:30 am", self.now), dt.datetime(2026, 11, 8, 9, 30))
        self.assertEqual(aa.parse_when("on monday", self.now), dt.datetime(2026, 11, 9, 9, 0))
        self.assertIsNone(aa.parse_when("send it", self.now))


if __name__ == "__main__":
    unittest.main()
