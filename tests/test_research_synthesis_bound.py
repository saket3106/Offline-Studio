import unittest
from agent_runtime import repeated_research_synthesis,agent_action_schema

class ResearchSynthesisTests(unittest.TestCase):
    def test_repeated_read_can_synthesize(self):
        self.assertTrue(repeated_research_synthesis('Research a motorcycle then state its vehicle type',{'alreadyRetrieved':True,'sources':[{'id':'actual'}]},False))
        self.assertEqual(len(agent_action_schema(set())['oneOf']),1)

    def test_side_effects_workspace_errors_and_missing_evidence_stay_open(self):
        for prompt,value,workspace in [('Research then save a procedure',{'alreadyRetrieved':True,'sources':[1]},False),('Research a motorcycle',{'alreadyRetrieved':True,'sources':[1]},True),('Research a motorcycle',{'alreadyRetrieved':False,'sources':[1]},False),('Research a motorcycle',{'alreadyRetrieved':True,'sources':[]},False),('Research a motorcycle',{'alreadyRetrieved':True,'sources':[1],'error':'failure'},False),('Find a photo and generate an image',{'alreadyRetrieved':True,'sources':[1]},False)]:
            with self.subTest(prompt=prompt,value=value,workspace=workspace):self.assertFalse(repeated_research_synthesis(prompt,value,workspace))
