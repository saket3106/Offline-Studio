import os, sys, tempfile, threading, time, unittest
from types import SimpleNamespace
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import assistant_actions as aa
import pc_control as pc
from assistant_agent import AssistantAgent
from assistant_host import AssistantHost


class QuickCommands(unittest.TestCase):
    def test_common_commands_are_instant(self):
        cases = {
            "volume 30": ("volume", {"level": 30}), "set the volume to 70%": ("volume", {"level": 70}),
            "turn the volume up": ("volume", {"change": "up"}), "mute": ("volume", {"change": "mute"}),
            "pause the music": ("media", {"action": "play_pause"}), "next song": ("media", {"action": "next"}),
            "brightness 40": ("brightness", {"level": 40}), "take a screenshot": ("screenshot", {}),
            "set a timer for 5 minutes": ("timer", {"minutes": 5.0, "label": ""}), "10 minute timer for pasta": ("timer", {"minutes": 10.0, "label": "pasta"}),
            "open my downloads": ("open_folder", {"name": "downloads"}), "open wifi settings": ("open_settings", {"page": "wifi"}),
            "close spotify": ("close_app", {"name": "spotify"}), "lock my pc": ("lock_pc", {}), "what's my battery": ("system_status", {}),
            "find my resume": ("find_files", {"query": "resume"}),
            "is my laptop charging right now": ("system_status", {}),
            "set a timer for one unit": ("timer", {"minutes": 1, "label": ""}), "set a timer of two minits": ("timer", {"minutes": 2, "label": ""}), "show desktop": ("show_desktop", {}),
            "open youtube.com": ("open_website", {"url": "youtube.com"}),
        }
        for text, (tool, args) in cases.items():
            steps = pc.quick_command(text)
            self.assertEqual(steps, [{"tool": tool, "args": args}], text)

    def test_chat_and_voice_controls_are_not_quick_commands(self):
        for text in ["close this live voice mode", "what is machine learning", "play a game with me and tell a story", "close the chat"]:
            self.assertIsNone(pc.quick_command(text), text)


class Control(unittest.TestCase):
    def test_volume_level_uses_key_steps_and_close_refuses_system(self):
        keys = []
        c = pc.PCControl(keypress=keys.append, runner=lambda cmd: SimpleNamespace(returncode=0, stdout=""))
        c.volume(level=30)
        self.assertEqual(keys.count(pc.VK["volume_down"]), 50); self.assertEqual(keys.count(pc.VK["volume_up"]), 15)
        with self.assertRaises(RuntimeError): c.close_app("explorer")
        calls = []
        c.runner = lambda cmd: calls.append(cmd) or SimpleNamespace(returncode=0, stdout="")
        c.close_app("spotify"); self.assertEqual(calls[-1], ["taskkill", "/IM", "spotify.exe"])  # graceful, no /F

    def test_open_file_only_user_files_and_never_programs(self):
        opened = []
        c = pc.PCControl(starter=opened.append)
        with tempfile.TemporaryDirectory(dir=os.environ.get("USERPROFILE")) as d:
            doc = os.path.join(d, "notes.txt"); open(doc, "w").close()
            exe = os.path.join(d, "setup.exe"); open(exe, "w").close()
            c.open_file(doc); self.assertEqual(opened, [doc])
            with self.assertRaises(RuntimeError): c.open_file(exe)
        with self.assertRaises(RuntimeError): c.open_file(r"C:\Windows\System32\drivers\etc\hosts")


class AgentRuns(unittest.TestCase):
    def make(self, auto_low=True, planner=None):
        self.events, self.launched, self.keys = [], [], []
        apps = [{"name": "Spotify", "source": "start menu", "target": "spotify.lnk"}, {"name": "Notepad", "source": "windows", "target": "notepad.exe"}]
        index = aa.AppIndex(providers=[lambda: apps])
        power = SimpleNamespace(applied=[], preview=lambda m: {"mode": m, "target": {"name": "High performance"}},
                                apply=lambda p: (power.applied.append(p["mode"]), {"plan": "High performance", "gameMode": True})[1])
        self.power = power
        tmp = tempfile.mkdtemp()
        host = AssistantHost(tmp, lambda: {}, self.events.append, app_index=index, power=power, launcher=lambda a: self.launched.append(a["target"]))
        control = pc.PCControl(keypress=self.keys.append, starter=self.launched.append, app_index=index)
        return AssistantAgent(host, control, self.events.append, lambda: {"assistant_auto_low_risk": auto_low}, planner=planner)

    def wait(self, agent, run_id, statuses=("done", "error", "cancelled", "awaiting"), timeout=3):
        end = time.time() + timeout
        while time.time() < end:
            if agent.runs[run_id]["status"] in statuses: return agent.runs[run_id]
            time.sleep(0.01)
        self.fail(agent.runs[run_id])

    def test_low_risk_runs_immediately(self):
        agent = self.make()
        run = self.wait(agent, agent.start("volume up")["id"], ("done",))
        self.assertEqual(run["route"], "rules"); self.assertEqual(run["steps"][0]["status"], "done"); self.assertTrue(self.keys)

    def test_confirm_tier_waits_for_allow(self):
        agent = self.make()
        run = agent.start("I feel like playing spotify")  # gaming → power_mode (confirm) then open_app
        run = self.wait(agent, run["id"], ("awaiting",))
        self.assertEqual(run["steps"][0]["tool"], "power_mode"); self.assertEqual(self.power.applied, [])
        agent.decide(run["id"], 0, True)
        run = self.wait(agent, run["id"], ("done",))
        self.assertEqual(self.power.applied, ["gaming"]); self.assertEqual(self.launched, ["spotify.lnk"])

    def test_skip_and_auto_run_off(self):
        agent = self.make(auto_low=False)
        run = self.wait(agent, agent.start("open notepad")["id"], ("awaiting",))
        agent.decide(run["id"], 0, False)
        run = self.wait(agent, run["id"], ("done",))
        self.assertEqual(run["steps"][0]["status"], "skipped"); self.assertEqual(self.launched, [])

    def test_model_plans_multi_step_requests(self):
        planner = lambda text: {"steps": [{"tool": "open_app", "args": {"name": "spotify"}}, {"tool": "volume", "args": {"level": "30"}},
                                          {"tool": "format_disk", "args": {}}], "reply": "Opening Spotify at 30% volume."}
        agent = self.make(planner=planner)
        run = self.wait(agent, agent.start("get some tunes going quietly")["id"], ("done",))
        self.assertEqual(run["route"], "model"); self.assertEqual([s["tool"] for s in run["steps"]], ["open_app", "volume"])  # unknown tool dropped
        self.assertEqual(self.launched, ["spotify.lnk"]); self.assertEqual(run["reply"], "Opening Spotify at 30% volume.")

    def test_compound_commands_split_or_go_to_the_model(self):
        calls = []
        agent = self.make(planner=lambda text: calls.append(text) or {"steps": [], "reply": "ok"})
        steps, _, route = agent.plan("open notepad and volume 30, then take a screenshot")
        self.assertEqual(route, "rules"); self.assertEqual([s["tool"] for s in steps], ["open_app", "volume", "screenshot"]); self.assertEqual(calls, [])
        _, _, route = agent.plan("open notepad and write my grocery list in it")
        self.assertEqual(route, "model"); self.assertEqual(len(calls), 1)  # one part not understood → model plans the whole

    def test_quick_buttons_refuse_confirm_tier(self):
        agent = self.make()
        self.assertFalse(agent.quick("lock_pc")["ok"]); self.assertTrue(agent.quick("media", {"action": "next"})["ok"])


if __name__ == "__main__":
    unittest.main()
