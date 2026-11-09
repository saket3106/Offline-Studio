"""Pure presentation boundaries; actual Qt behavior is tested separately. No model loads."""
import json, shutil, subprocess, unittest
from pathlib import Path

SOURCE=Path(__file__).resolve().parents[1]

class PresentationBoundaryTests(unittest.TestCase):
    def test_measurements_preferences_search_and_real_image_filters(self):
        module=(SOURCE/'frontend-source/src/presentation.js').as_uri()
        code=r'''
import assert from 'node:assert/strict';
import {boundedNumber,measuredGiB,settingsMatches,recentStudioImages} from MODULE;
assert.equal(boundedNumber('Infinity',860,640,1120),860);
assert.equal(boundedNumber(99999,860,640,1120),1120);
assert.equal(boundedNumber(1,15,13,20),13);
assert.equal(boundedNumber(null,15,13,20),15);
assert.equal(measuredGiB(undefined),null);
assert.equal(measuredGiB(null),null);
assert.equal(measuredGiB(-1),null);
assert.equal(measuredGiB(Infinity),null);
assert.equal(measuredGiB(0),'0.0 GiB');
assert.equal(measuredGiB(3*1024**3),'3.0 GiB');
assert(settingsMatches(['Chat','Models & chat',null,'Local inference settings'],'  inference '));
assert(!settingsMatches(['Chat','Models & chat',null,'Local inference settings'],'voice'));
const images=[{path:'C:\\local\\one.png'},{path:'c:/local/one.png'},{path:'two.png',hidden:true},{path:'three.png',deleted:true},{path:'four.png',deletedAt:1},{path:'five.png',deleted_at:1},{prompt:'no path'},{path:'six.png'}];
const before=JSON.stringify(images);
assert.deepEqual(recentStudioImages(images).map(i=>i.path),['C:\\local\\one.png','six.png']);
assert.equal(JSON.stringify(images),before);
assert.equal(recentStudioImages(Array.from({length:99},(_,n)=>({path:`${n}.png`}))).length,12);
console.log('16 presentation boundary checks passed');
'''.replace('MODULE',json.dumps(module))
        r=subprocess.run([shutil.which('node'),'--input-type=module','-e',code],capture_output=True,text=True,timeout=15)
        self.assertEqual(r.returncode,0,r.stderr)

    def test_existing_bridge_operations_are_preserved_and_no_network_fonts(self):
        source=(SOURCE/'frontend-source/src/main.jsx').read_text(encoding='utf-8')
        for handler in ['startAgentWithAttachments','sendMessage','saveSettingsConfirmed','toggleLiveVoiceMode','onLiveVoiceToggle','refreshLibrary','ModelSelector','SettingsDialog']:
            self.assertIn(handler,source)
        for name in ['refinement.css','presentation.js','product.jsx']:
            data=(SOURCE/'frontend-source/src'/name).read_text(encoding='utf-8')
            self.assertNotIn('fonts.googleapis.com',data)
            self.assertNotIn('Math.random',data)
        styles=(SOURCE/'frontend-source/src/styles.css').read_text(encoding='utf-8')
        for token in ['text-primary','text-secondary','text-muted','border-subtle']:
            self.assertNotIn('rgb(var(--'+token+'))',styles)

    def test_chat_settings_expose_only_the_bundled_offline_runtime(self):
        source=(SOURCE/'frontend-source/src/main.jsx').read_text(encoding='utf-8')
        self.assertIn('Offline Studio · built-in local engine',source)
        self.assertNotIn('LM Studio · optional external engine',source)
        self.assertNotIn('LM Studio model ID',source)

if __name__=='__main__':unittest.main()
