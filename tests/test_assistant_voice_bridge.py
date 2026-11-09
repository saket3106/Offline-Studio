import json, os, sys, tempfile, unittest
from types import SimpleNamespace
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app
import assistant_actions as aa
from assistant_host import AssistantHost


class FakePower:
    def preview(self, mode): return {"mode": mode, "target": {"guid": "g", "name": "High performance"}, "current": None, "gameMode": True}
    def apply(self, preview): return {"ok": True, "plan": "High performance", "gameMode": True}


class VoiceAssistantBridgeTests(unittest.TestCase):
    """Live Voice: 'play GTA 5' asks first; spoken yes runs it; spoken no cancels; chat falls through."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.launched, self.events, self.spoken = [], [], []
        apps = [{"name": "Grand Theft Auto V", "source": "steam", "target": "steam://rungameid/271590"}]
        self.host = AssistantHost(self.tmp.name, lambda: {}, self.events.append, app_index=aa.AppIndex(providers=[lambda: apps]),
                                  power=FakePower(), launcher=lambda a: self.launched.append(a["target"]))
        self.app = SimpleNamespace(frontend_bridge=SimpleNamespace(_assistant_host=lambda: self.host),
                                   emit_frontend=self.events.append)
        speak = patch.object(app.App, '_speak_voice_assistant', side_effect=lambda s, t, c, sid, text: self.spoken.append(text))
        speak.start(); self.addCleanup(speak.stop)

    def say(self, text):
        return app.App._voice_assistant(self.app, 'turn', 'chat', 'sid', text)

    def test_play_asks_then_yes_launches(self):
        self.assertTrue(self.say("I'm feeling like playing GTA 5"))
        self.assertIn('Say yes', self.spoken[-1]); self.assertEqual(self.launched, [])
        self.assertEqual(self.events[-1]['type'], 'assistantAction')
        self.assertTrue(self.say('Yes.'))
        self.assertEqual(self.launched, ['steam://rungameid/271590']); self.assertIn('Launching Grand Theft Auto V', self.spoken[-1])

    def test_no_cancels(self):
        self.say('launch gta 5'); self.assertTrue(self.say('no thanks'))
        self.assertEqual(self.launched, []); self.assertEqual(self.spoken[-1], 'Okay, cancelled.')

    def test_instant_voice_commands_and_spoken_confirmation(self):
        import pc_control
        from assistant_agent import AssistantAgent
        keys, follows = [], []
        agent = AssistantAgent(self.host, pc_control.PCControl(keypress=keys.append), self.events.append, lambda: {})
        self.app.frontend_bridge._assistant_agent = lambda: agent
        follow = patch.object(app.App, '_voice_assistant_follow', side_effect=lambda s, t, c, sid, a, rid, waited=0: follows.append(rid))
        follow.start(); self.addCleanup(follow.stop)
        self.assertTrue(self.say('Volume up.'))
        run = agent.runs[follows[-1]]
        for _ in range(100):
            if run['status'] == 'done': break
            import time; time.sleep(0.01)
        self.assertTrue(keys)  # ran without asking: low risk
        self.assertTrue(self.say('lock my pc'))
        rid = follows[-1]
        for _ in range(100):
            if agent.runs[rid]['status'] == 'awaiting': break
            import time; time.sleep(0.01)
        self.assertEqual(agent.voice_waiting(), (rid, 0))
        self.assertTrue(self.say('no'))  # spoken answer skips the waiting lock step
        for _ in range(100):
            if agent.runs[rid]['status'] == 'done': break
            import time; time.sleep(0.01)
        self.assertEqual(agent.runs[rid]['steps'][0]['status'], 'skipped')

    def test_misheard_or_unusual_controls_are_planned_by_the_model(self):
        import time, pc_control
        from assistant_agent import AssistantAgent
        keys, follows, delivered = [], [], []
        plans = {"could you make it a bit louder for me": {"steps": [{"tool": "volume", "args": {"change": "up"}}], "reply": ""},
                 "play me something on the radio about timers": {"steps": [], "reply": "chat"}}
        agent = AssistantAgent(self.host, pc_control.PCControl(keypress=keys.append), self.events.append, lambda: {},
                               planner=lambda text: plans[text])
        self.app.frontend_bridge._assistant_agent = lambda: agent
        self.app.frontend_bridge.assistantMainCall = SimpleNamespace(emit=lambda fn: fn())
        for name, fn in (('_voice_assistant_follow', lambda s, t, c, sid, a, rid, waited=0: follows.append(rid)),
                         ('_deliver_voice_transcript', lambda s, t, c, sid, text: delivered.append(text))):
            p = patch.object(app.App, name, side_effect=fn); p.start(); self.addCleanup(p.stop)
        # Real transcript from the user's session: "minute" heard as "unit" — the rules now accept it.
        self.assertEqual(pc_control.quick_command('Set a timer for one unit')[0]['tool'], 'timer')
        self.assertTrue(self.say('could you make it a bit louder for me'))
        for _ in range(200):
            if follows and agent.runs[follows[-1]]['status'] == 'done': break
            time.sleep(0.01)
        self.assertTrue(keys)  # the model's plan ran
        self.assertTrue(self.say('play me something on the radio about timers'))
        for _ in range(200):
            if delivered: break
            time.sleep(0.01)
        self.assertEqual(delivered, ['play me something on the radio about timers'])  # no steps → normal chat

    def test_ordinary_speech_goes_to_chat(self):
        self.assertFalse(self.say('what is machine learning'))
        self.assertEqual(self.spoken, [])


if __name__ == '__main__':
    unittest.main()
