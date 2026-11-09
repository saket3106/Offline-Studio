"""Independent count/coverage and exact-path alias regression counterexamples."""
import asyncio,json,os,sqlite3,tempfile,threading,unittest
from pathlib import Path
from workspace_services import group_library_aliases,library_asset_key,LocalWorkspace,migrate_database
from agent_runtime import verified_inventory_count,bound_observation_payload,AgentRuntime
from agent_workspace import WorkspaceAccess

class ApplicationRepairTests(unittest.TestCase):
 def test_known_projector_family_conflicts_are_not_filename_inferred(self):
  from model_runtime import vision_pair_conflict
  self.assertTrue(vision_pair_conflict({'general.architecture':'qwen3vl'},{'general.name':'Qwen3.5-9B'}))
  self.assertTrue(vision_pair_conflict({'general.architecture':'qwen35'},{'general.name':'Qwen3Vl 8b Instruct'}))
  self.assertFalse(vision_pair_conflict({'general.architecture':'qwen35'},{'general.name':'Qwen3.5-9B'}))
  self.assertFalse(vision_pair_conflict({'general.architecture':'unknown'},{'general.name':'Unknown'}))

 def test_count_never_uses_truncated_or_unknown_enumeration(self):
  prompt='How many files are in this folder?'
  for result in [{'files':[{}]*104,'truncated':True},{'enumerationComplete':False,'totalFiles':104},{'enumerationComplete':True,'totalFiles':None},{'enumerationComplete':True,'totalFiles':True},{'enumerationComplete':True,'totalFiles':104,'error':'failed'}]:
   self.assertFalse(verified_inventory_count(prompt,'list_workspace_files',result))
  self.assertFalse(verified_inventory_count('Count files and summarize their contents','list_workspace_files',{'enumerationComplete':True,'totalFiles':104}))

 def test_actual_enumeration_retains_authoritative_count_through_budget(self):
  with tempfile.TemporaryDirectory() as folder:
   for n in range(104):(Path(folder)/('file-'+str(n)+'-'+'x'*60+'.txt')).write_text('synthetic')
   access=WorkspaceAccess(folder)
   try:result=access.files()
   finally:access.close()
   self.assertTrue(result['enumerationComplete']);self.assertEqual(result['totalFiles'],104)
   bounded=bound_observation_payload(result,5500)
   self.assertTrue(bounded['omitted']);self.assertFalse(bounded['executionFailed'])
   self.assertEqual(bounded['totalFiles'],104)
   self.assertTrue(verified_inventory_count('How many files are in the folder?','list_workspace_files',bounded))

 def test_controller_count_completes_but_content_review_remains_partial(self):
  with tempfile.TemporaryDirectory() as folder:
   result={'files':[{'path':str(i)+'x'*90+'.txt'} for i in range(104)],'totalFiles':104,'enumerationComplete':True,'truncated':False}
   class Client:
    def __init__(self,*a,**k):pass
    async def __aenter__(self):return self
    async def __aexit__(self,*a):pass
    async def call(self,*a,**k):return result
   for prompt,expected in [('How many files are in this folder?','COMPLETED'),('List files and review every file','PARTIAL')]:
    plans=iter([json.dumps({'tool':'list_workspace_files','arguments':{}}),json.dumps({'final':'104 permitted files were enumerated; excerpts are bounded.'})])
    runtime=AgentRuntime(lambda *_:next(plans),folder,None,'fixture',lambda _:None,client_factory=Client);runtime.max_steps=2
    asyncio.run(runtime.run(prompt));self.assertEqual(runtime.state,expected)
    self.assertEqual(runtime.traces[0]['status'],'completed');self.assertEqual(runtime.traces[0]['observationCoverage'],'bounded')

 def test_similar_images_with_distinct_paths_do_not_merge(self):
  with tempfile.TemporaryDirectory() as folder:
   a=str(Path(folder)/'one.png');b=str(Path(folder)/'two.png')
   original=[{'id':'a','path':a,'prompt':'same'},{'id':'b','path':b,'prompt':'same'},{'id':'c','path':a,'userPrompt':'rich','messageId':7}]
   groups=group_library_aliases(original)
   self.assertEqual(len(groups),2);self.assertEqual(groups[0]['id'],'c');self.assertEqual(groups[0]['aliasIds'],['a','c']);self.assertNotIn('aliasIds',original[0])

 def test_relative_alias_hide_restore_keeps_bytes_and_unrelated_item(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);p=root/'car.png';p.write_bytes(b'original pixels');other=root/'other.png';other.write_bytes(b'other pixels')
   con=sqlite3.connect(':memory:');con.executescript("CREATE TABLE chats(id TEXT);CREATE TABLE messages(id INTEGER,chat_id TEXT,role TEXT,content TEXT,created REAL,attachment TEXT,metrics TEXT);CREATE TABLE library_images(id TEXT PRIMARY KEY,path TEXT,deleted INTEGER DEFAULT 0,user_prompt TEXT DEFAULT '');")
   migrate_database(con,root);con.executemany('INSERT INTO library_images(id,path) VALUES(?,?)',[('relative','car.png'),('absolute',str(p)),('other',str(other))]);con.commit()
   ws=LocalWorkspace(con,threading.RLock(),root)
   self.assertEqual(library_asset_key('car.png',root),library_asset_key(p,root))
   self.assertEqual(ws.manage_library(['absolute'],'hide')['completed'],2)
   self.assertEqual(dict(con.execute('SELECT id,deleted FROM library_images')),{'relative':1,'absolute':1,'other':0})
   self.assertEqual(ws.manage_library(['relative'],'restore')['completed'],2)
   self.assertEqual(p.read_bytes(),b'original pixels');self.assertEqual(other.read_bytes(),b'other pixels');con.close()

if __name__=='__main__':unittest.main()
