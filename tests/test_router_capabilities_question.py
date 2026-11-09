import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from router import route_request, get_relevant_tools


class CapabilitiesQuestionRouting(unittest.TestCase):
    """Asking about the assistant is conversation: no tool schemas (they cost 2.4 s per voice turn)."""

    def test_capabilities_question_is_not_tool_required(self):
        for text in ["explain about what are the capabilities of yours", "tell me about your capabilities"]:
            analysis = route_request(text)
            self.assertNotEqual(analysis.get("category"), "tool_required", text)
            self.assertFalse(analysis.get("wants_agent"), text)

    def test_explicit_tool_request_still_uses_tools(self):
        analysis = route_request("use your tools to solve this step by step")
        self.assertTrue(analysis.get("wants_agent"))


if __name__ == "__main__":
    unittest.main()
