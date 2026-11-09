"""Build-only signature-origin regression tests; synthetic PE files never execute."""
from pathlib import Path
import unittest,tempfile,struct,json,hashlib,sys,types
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import in_place_packaging as p

def image(payload=b'AAAAAAAA',checksum=1):
    data=bytearray(1024+8+len(payload));data[:2]=b'MZ';struct.pack_into('<I',data,0x3c,128)
    data[128:132]=b'PE\0\0';struct.pack_into('<HHIIIHH',data,132,0x8664,1,12345,0,0,240,0x2022)
    opt=152;struct.pack_into('<H',data,opt,0x20b)
    struct.pack_into('<I',data,opt+16,4096);struct.pack_into('<Q',data,opt+24,0x180000000)
    struct.pack_into('<II',data,opt+32,4096,512);struct.pack_into('<II',data,opt+56,8192,512)
    struct.pack_into('<I',data,opt+64,checksum);struct.pack_into('<I',data,opt+108,16)
    struct.pack_into('<II',data,opt+112+4*8,1024,8+len(payload))
    sec=392;data[sec:sec+8]=b'.text\0\0\0';struct.pack_into('<IIII',data,sec+8,4,4096,512,512)
    struct.pack_into('<I',data,sec+36,0x60000020);data[512:516]=b'code'
    struct.pack_into('<IHH',data,1024,8+len(payload),0x200,2);data[1032:]=payload
    return bytes(data)

class NativePins(unittest.TestCase):
    def fixture(self,root):
        a=root/'app';b=root/'sdk';a.mkdir();b.mkdir();(a/'Offline GPT.exe').write_bytes(b'not executable test fixture')
        old=a/'fixture.dll';new=b/'fixture.dll';old.write_bytes(image());new.write_bytes(image(b'BBBBBBBBBBBBBBBB',2))
        authority=root/'authority.json';authority.write_text('synthetic reviewed test fixture, not native acceptance')
        sign=lambda path:{'Path':str(path),'Status':'Valid','Subject':'SYNTHETIC_TEST_ONLY','Thumbprint':'fixture'}
        pair={'destination':'fixture.dll','kind':'BINARY','buildInput':str(new),'buildSha256':p.digest(new),'installedInput':str(old),'installedSha256':p.digest(old),'normalizedImageSha256':p.native_image_digest(old.read_bytes()),'installedAuthenticode':sign(old),'buildAuthenticode':sign(new)}
        proof={'schemaVersion':1,'status':'PASS','purpose':'PIN_INSTALLED_ORIGINALS_ONLY','installedExeSha256':p.digest(a/'Offline GPT.exe'),'authorityReceipts':[{'path':str(authority),'sha256':p.digest(authority)}],'pairs':[pair]}
        path=root/'proof.json';path.write_text(json.dumps(proof));compiled={'exeSha256':proof['installedExeSha256'],'nativeInputPinReceipt':str(path),'nativeInputPinSha256':p.digest(path)}
        approved={'entries':[{'name':'fixture.dll','kind':'BINARY','input':str(new),'inputSha256':p.digest(old)}]}
        return a,new,old,proof,path,compiled,approved
    def save(self,proof,path,compiled):path.write_text(json.dumps(proof));compiled['nativeInputPinSha256']=p.digest(path)
    def test_signing_only_and_certificate_size_variants(self):self.assertEqual(p.native_image_digest(image()),p.native_image_digest(image(b'B'*16,99)))
    def test_code_change_is_distinct(self):
        changed=bytearray(image());changed[512]^=1
        self.assertNotEqual(p.native_image_digest(image()),p.native_image_digest(changed))
    def test_other_header_change_is_distinct(self):
        changed=bytearray(image());changed[136]^=1
        self.assertNotEqual(p.native_image_digest(image()),p.native_image_digest(changed))
    def test_certificate_overlap_rejected(self):
        data=bytearray(image());struct.pack_into('<I',data,296,512)
        with self.assertRaisesRegex(ValueError,'overlay'):p.native_image_digest(data)
    def test_trailing_overlay_rejected(self):
        with self.assertRaisesRegex(ValueError,'overlay'):p.native_image_digest(image()+b'x')
    def test_invalid_certificate_type_rejected(self):
        data=bytearray(image());struct.pack_into('<H',data,1030,1)
        with self.assertRaisesRegex(ValueError,'WIN_CERTIFICATE'):p.native_image_digest(data)
    def test_valid_explicit_pair(self):
        with tempfile.TemporaryDirectory() as d:
            a,_,_,_,_,c,approved=self.fixture(Path(d));self.assertEqual(len(p.native_pin_inputs(approved,a,c)),1)
    def test_changed_raw_input_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a,new,_,_,_,c,approved=self.fixture(Path(d));new.write_bytes(image(b'C'*16,2))
            with self.assertRaisesRegex(ValueError,'raw identity'):p.native_pin_inputs(approved,a,c)
    def test_rehashed_code_change_still_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a,new,_,proof,path,c,approved=self.fixture(Path(d));data=bytearray(new.read_bytes());data[512]^=1;new.write_bytes(data)
            proof['pairs'][0]['buildSha256']=p.digest(new);self.save(proof,path,c)
            with self.assertRaisesRegex(ValueError,'executable image'):p.native_pin_inputs(approved,a,c)
    def test_unverified_signature_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a,_,_,proof,path,c,approved=self.fixture(Path(d));proof['pairs'][0]['buildAuthenticode']['Status']='UnknownError';self.save(proof,path,c)
            with self.assertRaisesRegex(ValueError,'signing identity'):p.native_pin_inputs(approved,a,c)
    def test_duplicate_destination_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a,_,_,proof,path,c,approved=self.fixture(Path(d));proof['pairs']*=2;self.save(proof,path,c)
            with self.assertRaisesRegex(ValueError,'Duplicate'):p.native_pin_inputs(approved,a,c)
    def test_proof_change_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a,_,_,_,path,c,approved=self.fixture(Path(d));path.write_text('{}')
            with self.assertRaisesRegex(ValueError,'review changed'):p.native_pin_inputs(approved,a,c)
    def test_authority_change_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a,_,_,proof,_,c,approved=self.fixture(Path(d));Path(proof['authorityReceipts'][0]['path']).write_text('altered')
            with self.assertRaisesRegex(ValueError,'authority changed'):p.native_pin_inputs(approved,a,c)
    def test_analysis_pins_original_exact_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);a,new,old,proof,path,c,approved=self.fixture(root)
            prior=root/'prior.json';prior.write_text(json.dumps(approved));binding=root/'compiled.json';binding.write_text(json.dumps(c))
            env=root/'environment.json';env.write_text(json.dumps({'priorCompatibilityReceipt':str(prior),'priorCompiledReceipt':str(binding)}))
            analysis=types.SimpleNamespace(binaries=[('fixture.dll',str(new),'BINARY')])
            with patch.object(p,'verify_build_environment'):
                pins=p.pin_analysis_native_inputs(analysis,a,env)
            self.assertEqual(len(pins),1);self.assertEqual(analysis.binaries,[('fixture.dll',str(old),'BINARY')]);self.assertEqual(p.digest(old),approved['entries'][0]['inputSha256'])
    def test_analysis_unexpected_origin_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);a,new,old,proof,path,c,approved=self.fixture(root);unexpected=root/'other.dll';unexpected.write_bytes(new.read_bytes())
            prior=root/'prior.json';prior.write_text(json.dumps(approved));binding=root/'compiled.json';binding.write_text(json.dumps(c));env=root/'environment.json';env.write_text(json.dumps({'priorCompatibilityReceipt':str(prior),'priorCompiledReceipt':str(binding)}))
            analysis=types.SimpleNamespace(binaries=[('fixture.dll',str(unexpected),'BINARY')])
            with patch.object(p,'verify_build_environment'),self.assertRaisesRegex(ValueError,'Unexpected Analysis native origin'):p.pin_analysis_native_inputs(analysis,a,env)
if __name__=='__main__':unittest.main(verbosity=2)
