"""Actual raster/SQLite reference tests; no inference or synthetic model claim."""
from pathlib import Path
from types import SimpleNamespace
import hashlib,json,sqlite3,tempfile,threading,time,unittest
from PIL import Image
from reference_workflow import ReferenceStore,prepare_reference,composite_subject,reference_capabilities,conditioning_evidence

class ReferenceCompletion(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.reference=self.root/'reference.png';self.background=self.root/'background.png'
        image=Image.new('RGB',(16,12));image.putdata([(i%255,(i*7)%255,(i*13)%255) for i in range(16*12)]);image.save(self.reference);Image.new('RGB',(24,20),(210,215,220)).save(self.background)
        self.con=sqlite3.connect(self.root/'data.sqlite3');self.addCleanup(self.con.close);self.ws=SimpleNamespace(con=self.con,lock=threading.RLock(),directory=self.root);self.store=ReferenceStore(self.ws)
    def prepared(self):return prepare_reference(self.reference,self.root/'knowledge/references',{'url':'https://upload.wikimedia.org/fixture.png','sourceUrl':'https://commons.wikimedia.org/wiki/File:fixture.png','license':'CC BY-SA 4.0','artist':'Fixture creator','sourceId':'K0123456789abcdef'})
    def test_prepare_uses_actual_safe_bytes_and_deduplicates(self):
        a=self.prepared();b=self.prepared();self.assertEqual(a['path'],b['path']);self.assertEqual(a['imageHash'],hashlib.sha256(Path(a['path']).read_bytes()).hexdigest());self.assertFalse(a['conditioningActive']);self.assertEqual((16,12),(a['width'],a['height']))
    def test_persistence_scope_metadata_and_delete_preserve_file(self):
        prepared=self.prepared();a=self.store.add(prepared,'project-a','run-1');b=ReferenceStore(self.ws).add(prepared,'project-a','run-2');self.assertEqual(a['id'],b['id']);self.assertEqual('run-2',b['runId']);self.assertEqual('CC BY-SA 4.0',b['license']);self.assertEqual([],self.store.list('project-b'))
        with self.assertRaises(PermissionError):self.store.get(a['id'],'project-b')
        self.store.remove(a['id'],'project-a');self.assertTrue(Path(a['path']).is_file());self.assertEqual([],self.store.list('project-a'))
    def test_direct_paths_require_trusted_picker_approval(self):
        with self.assertRaises(PermissionError):self.store.add({'path':str(self.reference)})
        self.assertTrue(self.store.add({'path':str(self.reference)},approved_path=True)['id'])
    def test_cache_scope_cannot_be_escaped_with_parent_components(self):
        cache=self.root/'knowledge/references';cache.mkdir(parents=True)
        with self.assertRaises(PermissionError):self.store.add({'path':str(cache/'../../reference.png')})
    def test_changed_missing_and_expired_saved_references_rejected(self):
        a=self.store.add(self.prepared());path=Path(a['path']);saved=path.read_bytes();path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'changed'):self.store.get(a['id'])
        path.write_bytes(saved);self.con.execute('UPDATE studio_references SET expires=1');self.con.commit()
        with self.assertRaisesRegex(ValueError,'expired'):self.store.get(a['id'])
        path.unlink()
        with self.assertRaisesRegex(ValueError,'missing'):self.store.get(a['id'])
    def test_hash_mismatch_and_active_source_url_rejected(self):
        a=self.prepared();a['imageHash']='0'*64
        with self.assertRaisesRegex(ValueError,'changed'):self.store.add(a)
        a=self.prepared();a['sourceUrl']='javascript:alert(1)'
        from research_network import ResearchError
        with self.assertRaises(ResearchError):self.store.add(a)
    def test_rectangle_composite_preserves_selected_subject_pixels(self):
        result=composite_subject(self.reference,self.background,self.root/'out',rectangle=[3,2,12,9]);receipt=json.loads(Path(result['provenancePath']).read_text());self.assertTrue(receipt['selectedPixelsExactlyPreserved']);self.assertEqual(63,receipt['preservedOpaquePixels']);self.assertFalse(receipt['generativeModelUsed']);self.assertFalse(receipt['automaticSegmentationUsed'])
        with Image.open(self.reference) as source,Image.open(result['path']) as output:
            self.assertEqual(source.crop((3,2,12,9)).tobytes(),output.crop((3,2,12,9)).tobytes());self.assertEqual((210,215,220),output.getpixel((0,0)))
    def test_explicit_mask_supports_exact_opaque_pixels_and_labeled_blending(self):
        mask=self.root/'mask.png';m=Image.new('L',(16,12));m.putpixel((4,5),255);m.putpixel((5,5),128);m.save(mask);r=composite_subject(self.reference,self.background,self.root/'out',mask_path=mask);self.assertEqual(1,r['metrics']['preservedOpaquePixels']);self.assertEqual(1,r['metrics']['blendedBoundaryPixels'])
        with Image.open(self.reference) as source,Image.open(r['path']) as output:self.assertEqual(source.getpixel((4,5)),output.getpixel((4,5)))
    def test_no_automatic_mask_or_invalid_rectangle(self):
        for rectangle in [None,[-1,0,5,5],[0,0,17,12],[0,0,16,12],[0,0,0,3],[0,0,True,5],[0,0,5.5,7]]:
            with self.subTest(rectangle=rectangle),self.assertRaises(ValueError):composite_subject(self.reference,self.background,self.root/'out',rectangle=rectangle)
    def test_mask_dimensions_must_match(self):
        path=self.root/'mask.png';Image.new('L',(8,8),255).save(path)
        with self.assertRaisesRegex(ValueError,'exactly'):composite_subject(self.reference,self.background,self.root/'out',mask_path=path)
    def test_cancellation_creates_no_output(self):
        cancel=threading.Event();cancel.set()
        with self.assertRaises(InterruptedError):composite_subject(self.reference,self.background,self.root/'out',rectangle=[1,1,8,8],cancel=cancel)
        self.assertFalse((self.root/'out').exists())
    def test_html_disguised_as_raster_is_never_prepared(self):
        path=self.root/'web.png';path.write_text('<svg onload="alert(1)"></svg>')
        with self.assertRaises(Exception):prepare_reference(path,self.root/'knowledge/references')
    def test_native_evidence_requires_actual_argument_and_unchanged_bytes(self):
        r=self.prepared()
        with self.assertRaisesRegex(ValueError,'actual native'):conditioning_evidence(r,['sd-cli.exe','-p',r['path']])
        record=conditioning_evidence(r,['sd-cli.exe','-r',r['path'],'-p','Edit the setting']);self.assertTrue(record['actualImageArgument']);self.assertFalse(record['inferenceVerified'])
        Path(r['path']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'hash changed'):conditioning_evidence(r,['sd-cli.exe','-r',r['path']])
    def test_capability_is_documented_and_runtime_probed_not_inferred_success(self):
        model=self.root/'flux-2-klein-base-9b-Q4_K_M.gguf';model.write_bytes(b'fixture header, not actual model');cfg={'flux_model':str(model)}
        self.assertEqual('UNAVAILABLE_OR_NOT_PROBED',reference_capabilities(cfg)['referenceEditing']);c=reference_capabilities(cfg,'-r, --ref-image Reference input');self.assertEqual('AVAILABLE_REQUIRES_NATIVE_ACCEPTANCE',c['referenceEditing']);self.assertFalse(c['inferenceVerified'])
        probed=reference_capabilities(cfg,'',{'--ref-image','--init-img'});self.assertTrue(probed['nativeReferenceFlag']);self.assertEqual('installed CLI help probe',probed['flagSource']);self.assertIn('--init-img',probed['nativeFlags']);self.assertFalse(probed['inferenceVerified'])

if __name__=='__main__':unittest.main()
