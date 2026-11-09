"""Real JavaScript lineage grouping, independent of screenshots or image pixels."""
import json,subprocess,unittest
from pathlib import Path

class LibraryViewFrontendTests(unittest.TestCase):
 def test_only_authoritative_alias_and_parent_relationships_group(self):
  module=Path(__file__).resolve().parents[1]/'frontend-source/src/libraryView.js'
  node=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
  code="import assert from 'node:assert/strict';import {groupVersionFamilies} from "+json.dumps(module.as_uri())+";"+'''
const a={id:'a',path:'one.png',aliasIds:['old-a']},b={id:'b',path:'two.png',parentId:'old-a'},c={id:'c',path:'three.png'};
let grouped=groupVersionFamilies([b,a,c]);assert.equal(grouped.length,2);assert.equal(grouped[0].id,'b');assert.equal(grouped[0].versionCount,2);assert.deepEqual(grouped[0].familyIds,['b','a']);assert.equal(a.versionCount,undefined);
assert.equal(groupVersionFamilies([{id:'a',path:'similar.png'},{id:'b',path:'similar2.png'}]).length,2);
assert.equal(groupVersionFamilies([{id:'a',parentId:'missing'},{id:'b'}]).length,2);
assert.equal(groupVersionFamilies([{id:'a',parentId:'b'},{id:'b',parentId:'a'}]).length,2);
assert.equal(groupVersionFamilies([{id:'a',parentId:'b',aliasMetadata:[{parentId:'c'}]},{id:'b'},{id:'c'}]).length,3);
console.log('12 lineage/identity assertions passed');
'''
  r=subprocess.run([str(node),'--input-type=module','-e',code],capture_output=True,text=True,timeout=15,creationflags=0x08000000)
  self.assertEqual(r.returncode,0,r.stderr);self.assertIn('assertions passed',r.stdout)

if __name__=='__main__':unittest.main()
