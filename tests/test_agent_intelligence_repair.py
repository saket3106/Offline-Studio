"""Independent routing/content/scope criteria; deterministic, NOT native inference."""
import asyncio,json,tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pymupdf
from PIL import Image
from agent_resources import AttachmentRegistry,AgentSpecialists,document_evidence
from agent_workspace import WorkspaceAccess
from agent_runtime import AgentRuntime,request_tool_policy,agent_action_schema,unauthorized_search_scope
from agent_mcp import validate_arguments,ToolContractError

class Client:
 calls=[]
 def __init__(self,*a,**kw):pass
 async def __aenter__(self):return self
 async def __aexit__(self,*a):pass
 async def call(self,name,args,**kw):
  self.calls.append((name,args))
  return {'inspected':[{'source':'status.txt','excerpt':'ORCHID-715; completion two days late; B-12; Arjun Mehta'}],'relevantFiles':1,'coverageComplete':True} if name=='inspect_workspace' else {'matches':[]}

class IntelligenceRepairTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);Client.calls=[]
 def pdf(self,name='report.pdf'):
  p=self.root/name;doc=pymupdf.open()
  for value in ['ALPHA: first physical page','BETA: second physical page']:doc.new_page().insert_text((72,72),value)
  doc.save(p);doc.close();return p
 def service(self,path):
  registry=AttachmentRegistry();record=registry.register([str(path)],'synthetic')[0]
  access=WorkspaceAccess(self.root);self.addCleanup(access.close)
  return registry,record,AgentSpecialists(SimpleNamespace(vision_model_status=lambda:{'visionAvailable':False,'visionMessage':'No configured vision backend'}),access,registry)
 def task(self,plans,prompt,resources=None,specialist=None):
  it=iter(plans);task=AgentRuntime(lambda *_:json.dumps(next(it)),self.root,None,'synthetic',lambda _:None,client_factory=Client)
  task.resources=resources or [];task.specialists=specialist;asyncio.run(task.run(prompt));return task
 def test_pdf_signature_overrides_image_filename(self):
  p=self.pdf();q=self.root/'misleading.png';q.write_bytes(p.read_bytes());r,record,s=self.service(q)
  self.assertEqual(record['mediaType'],'application/pdf');self.assertEqual(record['validatedSuffix'],'.pdf')
  with self.assertRaisesRegex(ValueError,'document'):s.read_image(record['id'])
 def test_pdf_physical_page_two_and_original_identity(self):
  p=self.pdf();before=p.read_bytes();r,record,s=self.service(p);v=s.call('read_attachment',{'source':record['id'],'page':'2'},threading.Event())
  self.assertIn('BETA',v['text']);self.assertNotIn('ALPHA',v['text']);self.assertEqual(v['metadata']['page_map'][0]['page'],2)
  self.assertEqual(v['name'],'report.pdf');self.assertTrue(v['coverage_complete']);self.assertEqual(p.read_bytes(),before)
 def test_invalid_pdf_page_never_falls_back_to_another_page(self):
  r,record,s=self.service(self.pdf())
  for page in ['0','3','-1','two','1.0']:
   with self.subTest(page=page),self.assertRaises(ValueError):s.call('read_attachment',{'source':record['id'],'page':page},threading.Event())
 def test_scanned_page_is_not_ocr_success(self):
  d=pymupdf.open();d.new_page();v=document_evidence(d.tobytes(),'scan.pdf','.pdf','1');d.close()
  self.assertFalse(v['ocrPerformed']);self.assertTrue(v['omitted']);self.assertEqual(v['scannedPagesRequiringOcr'],[1])
 def test_attachment_hash_is_rechecked(self):
  p=self.pdf();r,record,s=self.service(p);p.write_bytes(b'changed')
  with self.assertRaisesRegex(ValueError,'changed'):r.read(record['id'])
 def test_broken_image_does_not_register_as_visual_evidence(self):
  p=self.root/'fake.png';p.write_bytes(b'not pixels')
  with self.assertRaises((ValueError,OSError)):AttachmentRegistry().register([str(p)],'synthetic')
 def test_real_image_reports_missing_vision_without_filename_search(self):
  p=self.root/'image.png';Image.new('RGB',(16,16),'red').save(p);r,record,s=self.service(p)
  with self.assertRaisesRegex(RuntimeError,'VISION_UNAVAILABLE'):s.inspect_image(record['id'],'What objects are visible?',threading.Event())
  self.assertFalse(Client.calls)
 def test_missing_budget_uses_evidence_and_is_successful_absence(self):
  task=self.task([{'tool':'calculate','arguments':{'expression':'approved budget'}},{'tool':'inspect_workspace','arguments':{}},{'final':'The approved budget is not available in status.txt.'}],"What is the project's approved budget?")
  self.assertEqual(task.state,'COMPLETED');self.assertEqual([n for n,_ in Client.calls],['inspect_workspace']);self.assertNotIn('partial',task.final.casefold());self.assertNotIn('Runtime inspection',task.final)
 def test_invalid_calculator_contract_never_dispatches(self):
  for expression in ['approved budget','budget[0]','"123"','True+1','__import__("os")']:
   with self.subTest(expression=expression),self.assertRaises(ToolContractError):validate_arguments('calculate',{'expression':expression})
  self.assertEqual(validate_arguments('calculate',{'expression':'19*23'})['expression'],'19*23')
 def test_pdf_wrong_image_selection_repairs_without_dispatch(self):
  r,record,s=self.service(self.pdf());id=record['id']
  task=self.task([{'tool':'inspect_image','arguments':{'source':id,'question':'page two'}},{'tool':'read_attachment','arguments':{'source':id,'page':'2'}},{'final':'BETA is on physical page 2 of report.pdf.'}],'Fact on page 2 with its source page.',r.public(),s)
  self.assertEqual(task.state,'COMPLETED');self.assertFalse(Client.calls);self.assertEqual([t['tool'] for t in task.traces],['read_attachment'])
 def test_document_final_requires_actual_read(self):
  r,record,s=self.service(self.pdf())
  task=self.task([{'final':'It says invented information.'},{'final':'It says invented information.'}],'Summarize this PDF.',r.public(),s)
  self.assertEqual(task.state,'PARTIAL');self.assertIn('required source text was not read',task.final)
 def test_visible_objects_selects_actual_image_capability(self):
  policy=request_tool_policy('What objects are visible?',[{'mediaType':'image/png'}]);self.assertTrue(policy['visual']);self.assertIn('search_workspace',policy['excluded'])
 def test_mixed_attachments_preserve_both_modalities(self):
  p=request_tool_policy('Compare the image and PDF',[{'mediaType':'image/png'},{'mediaType':'application/pdf'}]);self.assertNotIn('inspect_image',p['excluded']);self.assertNotIn('read_attachment',p['excluded'])
 def test_dynamic_schema_matches_filtered_catalog(self):
  names=[v['properties'].get('tool',{}).get('enum',[None])[0] for v in agent_action_schema({'read_attachment'})['oneOf']]
  self.assertEqual(names,[None,'read_attachment'])
 def test_outside_scope_does_not_substitute_workspace(self):
  task=self.task([],'Search outside the authorized workspace for project information.')
  self.assertEqual(task.state,'ANSWERED');self.assertFalse(Client.calls);self.assertIn('not searched',task.final)
 def test_downloads_scope_requires_exact_authorization(self):
  task=self.task([],'Find images in Downloads.');self.assertIn('authorization required',task.final);self.assertFalse(Client.calls)
  self.assertEqual(unauthorized_search_scope('Search Downloads for pictures',self.root/'Downloads'),'')
  self.assertTrue(unauthorized_search_scope('Search Downloads for pictures',self.root/'Downloads'/'subfolder'))
 def test_search_receipt_identifies_actual_directory(self):
  task=self.task([{'tool':'search_workspace','arguments':{'query':'ORCHID'}},{'final':'No literal match in the authorized workspace.'}],'Find ORCHID in the workspace')
  self.assertEqual(task.traces[0]['output']['searchedScope'],str(self.root))
 def test_repeated_inspection_coverage_is_emitted_once(self):
  task=self.task([{'tool':'inspect_workspace','arguments':{}},{'tool':'inspect_workspace','arguments':{}},{'final':'status.txt identifies ORCHID-715.'}],'Analyze the workspace files')
  self.assertEqual(task.final.count('Runtime inspection coverage:'),1)

if __name__=='__main__':unittest.main()
