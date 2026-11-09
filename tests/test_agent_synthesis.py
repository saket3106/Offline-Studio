"""Status acknowledgments are not substantive workspace analysis results."""
import asyncio,json,tempfile,unittest
from pathlib import Path
try:
    from test_agent_orchestration import Client
except ModuleNotFoundError:
    from tests.test_agent_orchestration import Client
from agent_runtime import AgentRuntime

class AgentSynthesisTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);Client.calls=[]
  Client.results={'inspect_workspace':{'inspected':[{'source':'evidence.txt','excerpt':'Delivery status: delayed by two days.'}],'relevantFiles':1,'coverageComplete':True}}
 def run_agent(self,finals):
  plans=iter([{'tool':'inspect_workspace','arguments':{}}]+[{'final':x} for x in finals]);events=[]
  task=AgentRuntime(lambda *_:json.dumps(next(plans)),self.root,None,'synthetic-chat',events.append,client_factory=Client)
  asyncio.run(task.run('Analyze the workspace files and report useful findings.'));return task,events
 def test_status_only_final_is_retried_without_repeating_the_read(self):
  task,events=self.run_agent(['Analysis completed.','evidence.txt reports a two-day delivery delay.'])
  self.assertEqual(task.state,'COMPLETED');self.assertIn('two-day delivery delay',task.final)
  self.assertEqual([name for name,_ in Client.calls],['inspect_workspace'])
  self.assertTrue(any(e['state']=='VERIFYING' and 'findings' in e['summary'].lower() for e in events))
 def test_repeated_status_only_final_never_counts_as_completed_analysis(self):
  task,_=self.run_agent(['The review is complete.','Done.'])
  self.assertEqual(task.state,'PARTIAL');self.assertIn('findings',task.final.lower())
  self.assertEqual(len(Client.calls),1)
 def test_short_concrete_finding_is_preserved(self):
  task,_=self.run_agent(['evidence.txt: delivery delayed two days.'])
  self.assertEqual(task.state,'COMPLETED');self.assertIn('two days',task.final)

if __name__=='__main__':unittest.main()
