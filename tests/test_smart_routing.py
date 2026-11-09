"""One smart chat box: the message itself decides web research and Agent use (owner request 2026-11-09)."""
import unittest

from integrated_runtime import DEFAULT_CONFIG
from intelligence_engine import DEFAULTS, needs_web
from router import AGENT_ROUTE_SCHEMA, agent_route


class AgentRouteTests(unittest.TestCase):
    def test_multi_step_jobs_go_to_agent(self):
        for text in ('organize the files in my project folder', 'fix the bug in app.py', 'run the tests',
                     'create a file called notes.txt'):
            self.assertEqual(agent_route(text), 'agent', text)

    def test_ordinary_chat_stays_in_chat(self):
        for text in ('write a python function that reverses a list', 'generate an image of a red fox',
                     'what is a database schema', 'search the web about the iphone 17 price', 'hello'):
            self.assertEqual(agent_route(text), 'chat', text)

    def test_unclear_questions_ask_the_model(self):
        self.assertEqual(agent_route('how do I rename files in python'), 'maybe')

    def test_schema_allows_only_two_routes(self):
        self.assertEqual(set(AGENT_ROUTE_SCHEMA['properties']['route']['enum']), {'agent', 'chat'})


class RouteMessageSlotTests(unittest.TestCase):
    def route(self, text, root='', files=False, ready=False):
        import json
        from types import SimpleNamespace
        from app import DesktopBridge
        engine = SimpleNamespace(runtime=SimpleNamespace(ready=ready),
                                 chat_completion=lambda *a, **k: '{"route": "agent"}')
        bridge = SimpleNamespace(agent=SimpleNamespace(root=root), backend=SimpleNamespace(engines=engine))
        return json.loads(DesktopBridge.routeMessage.__wrapped__(bridge, text, files)
                          if hasattr(DesktopBridge.routeMessage, '__wrapped__')
                          else DesktopBridge.routeMessage(bridge, text, files))

    def test_agent_needs_a_workspace_or_file(self):
        self.assertEqual(self.route('organize the files in my project folder')['route'], 'chat')
        self.assertEqual(self.route('organize the files in my project folder', root='C:/work')['route'], 'agent')
        self.assertEqual(self.route('rename the attached files to dates', files=True)['route'], 'agent')

    def test_unclear_requests_ask_the_loaded_model(self):
        result = self.route('how do I rename files in python', root='C:/work', ready=True)
        self.assertEqual((result['route'], result['how']), ('agent', 'model'))
        self.assertEqual(self.route('how do I rename files in python', root='C:/work')['route'], 'chat')


class WebRouteTests(unittest.TestCase):
    def test_app_default_is_automatic_but_engine_fallback_stays_offline(self):
        self.assertEqual(DEFAULT_CONFIG['intelligence_mode'], 'hybrid')
        self.assertEqual(DEFAULTS['intelligence_mode'], 'offline')

    def test_asking_for_the_web_searches(self):
        for text in ('search the web about iphone 17 price', 'google it: best laptop 2026',
                     'check the websites for the release date', 'Search the web: capital of peru'):
            self.assertTrue(needs_web(text, 'hybrid'), text)

    def test_owner_phrases_search_only_when_asked(self):
        for text in ('take reference from web about this information',
                     'search for all info about ai models on web and summarize it to me',
                     'take a reference from web for indian car bike model for image generation'):
            self.assertTrue(needs_web(text, 'hybrid'), text)
        for text in ('Write a sick leave email to principal@example.com and schedule it to send today at 9 am',
                     'what is the latest iphone', 'get the net amount after tax', 'find the bug in this code',
                     'generate an image of a red indian motorbike'):
            self.assertFalse(needs_web(text, 'hybrid'), text)

    def test_saying_no_web_skips_it(self):
        for text in ("latest iphone price, don't search the web", 'current ceo of openai from what you know',
                     'iphone 17 price (answer from what you know, without the web)'):
            self.assertFalse(needs_web(text, 'hybrid'), text)

    def test_timeless_questions_stay_offline(self):
        self.assertFalse(needs_web('explain recursion', 'hybrid'))

    def test_never_use_internet_wins(self):
        self.assertFalse(needs_web('search the web about iphone 17 price', 'offline'))


if __name__ == '__main__':
    unittest.main()
