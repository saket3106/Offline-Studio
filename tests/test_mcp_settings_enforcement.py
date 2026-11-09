"""Settings must govern real dispatch, not just the displayed tool catalog."""
import asyncio,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from agent_mcp import MCPClientManager,MCPRegistry
from agent_runtime import AgentRuntime

class Dispatch:
    calls=[]
    def __init__(self,*a,**k):pass
    async def __aenter__(self):return self
    async def __aexit__(self,*a):pass
    async def call(self,tool,args,**kwargs):self.calls.append(tool);return {'value':6,'expression':'2*3'}

class SettingsEnforcement(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.registry=MCPRegistry();p=patch.object(MCPRegistry,'_instance',self.registry);p.start();self.addCleanup(p.stop);Dispatch.calls=[]
    def runtime(self,model):return AgentRuntime(model,self.root,None,'chat',lambda _:None,client_factory=Dispatch)
    def test_disabled_tool_never_reaches_workspace_transport(self):
        self.registry.toggle_tool('calculate',False)
        client=MCPClientManager(self.root)
        client.client=SimpleNamespace(call_tool=Mock(side_effect=AssertionError('Transport must not run')))
        with self.assertRaisesRegex(PermissionError,'disabled'):
            asyncio.run(client.call('calculate',{'expression':'2*3'}))
        client.client.call_tool.assert_not_called()
    def test_disabled_server_never_reaches_agent_dispatch(self):
        self.registry.toggle_server('system_shell_mcp',False)
        task=self.runtime(lambda *_:json.dumps({'tool':'calculate','arguments':{'expression':'2*3'}}))
        asyncio.run(task.run('Use the calculator'))
        self.assertEqual(Dispatch.calls,[]);self.assertEqual(task.state,'FAILED')
    def test_revoked_during_planning_is_checked_again(self):
        def model(*_):
            self.registry.toggle_tool('calculate',False)
            return json.dumps({'tool':'calculate','arguments':{'expression':'2*3'}})
        task=self.runtime(model);asyncio.run(task.run('Use the calculator'))
        self.assertEqual(Dispatch.calls,[]);self.assertIn('disabled',task.final.lower())
    def test_disabled_host_specialist_is_not_called(self):
        self.registry.toggle_tool('inspect_image',False)
        task=self.runtime(lambda *_:json.dumps({'tool':'inspect_image','arguments':{'source':'attachment:one','question':'Describe pixels'}}))
        specialist=Mock();task.specialists=SimpleNamespace(previews=[],call=specialist)
        asyncio.run(task.run('Describe the supplied image'))
        specialist.assert_not_called();self.assertEqual(Dispatch.calls,[])
    def test_disabled_tools_are_not_advertised_to_planner(self):
        self.registry.toggle_tool('calculate',False);seen=[]
        task=self.runtime(lambda messages,*_:(seen.append(messages[0]['content']) or json.dumps({'final':'No calculation was performed.'})))
        asyncio.run(task.run('Explain available capabilities'))
        catalog=seen[0].split('Catalog: ',1)[1].split('\nActual conversation resources',1)[0]
        self.assertNotIn('calculate',json.loads(catalog))
    def test_enabled_calculation_still_completes(self):
        plans=iter([{'tool':'calculate','arguments':{'expression':'2*3'}},{'final':'The result is 6.'}])
        task=self.runtime(lambda *_:json.dumps(next(plans)));asyncio.run(task.run('Use the calculator'))
        self.assertEqual(Dispatch.calls,['calculate']);self.assertEqual(task.state,'COMPLETED')
    def test_unknown_settings_do_not_report_success(self):
        with self.assertRaises(ValueError):self.registry.toggle_tool('invented-tool',False)
        with self.assertRaises(ValueError):self.registry.toggle_server('invented-server',False)
    def test_revocation_during_approval_blocks_write_before_journaling(self):
        task=self.runtime(lambda *_:json.dumps({'tool':'write_local_file','arguments':{'path':'result.txt','content':'Do not write'}}))
        def approve(*args):
            self.registry.toggle_tool('write_local_file',False)
            return args[2]
        task.broker=SimpleNamespace(request=approve,cancel=Mock())
        asyncio.run(task.run('Write a new file'))
        self.assertEqual(Dispatch.calls,[]);self.assertFalse((self.root/'result.txt').exists())
        self.assertIn('disabled before dispatch',task.final.lower())

if __name__=='__main__':unittest.main()
