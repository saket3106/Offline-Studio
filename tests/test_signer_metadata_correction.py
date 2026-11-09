"""An explicit correction permits only reviewed certificate metadata, never new inputs."""
import copy,json,tempfile,unittest
from pathlib import Path
import in_place_packaging as packaging
import tests.test_native_pin_lineage as lineage

class SignerCorrectionTests(unittest.TestCase):
 def fixture(self,root):
  helper=lineage.RepeatPinLineage();values=helper.fixture(root)
  installed,build,payload,historical,history_path,fresh,path,compiled,approved=values
  original=copy.deepcopy(historical['pairs'][0]);fresh['pairs'][0]['buildAuthenticode']['Thumbprint']='actual-reviewed-certificate'
  helper.save(fresh,path,compiled)
  review={'purpose':'OWNER_APPROVED_EXACT_SIGNER_METADATA_CORRECTION','reviewStatus':'OWNER_APPROVED','ownerApproval':'explicit synthetic owner decision','installedExeSha256':compiled['exeSha256'],'historicalProofSha256':approved['nativeInputPins']['sha256'],'correctedProofSha256':compiled['nativeInputPinSha256'],'corrections':[{'originalPair':original,'correctedPair':copy.deepcopy(fresh['pairs'][0])}]}
  receipt=root/'signer-review.json';self.save(review,receipt,compiled)
  return values,review,receipt
 def save(self,review,path,compiled):
  path.write_text(json.dumps(review));compiled.update(signerMetadataCorrectionReceipt=str(path),signerMetadataCorrectionSha256=packaging.digest(path))
 def test_approved_exact_metadata_correction_preserves_payload_and_history(self):
  with tempfile.TemporaryDirectory() as folder:
   values,review,path=self.fixture(Path(folder));old=values[4].read_bytes()
   pins=packaging.native_pin_inputs(values[8],values[0],values[7])
   self.assertEqual(pins[0]['buildAuthenticode']['Thumbprint'],'actual-reviewed-certificate');self.assertEqual(values[4].read_bytes(),old)
 def test_missing_pending_or_tampered_review_is_rejected(self):
  for change in ['missing','pending','tamper','scope','baseline','historical-proof','corrected-proof','owner']:
   with self.subTest(change=change),tempfile.TemporaryDirectory() as folder:
    values,review,path=self.fixture(Path(folder));compiled=values[7]
    if change=='missing':compiled.pop('signerMetadataCorrectionReceipt')
    elif change=='pending':review['reviewStatus']='PENDING'
    elif change=='scope':review['corrections']=[]
    elif change=='baseline':review['installedExeSha256']='0'*64
    elif change=='historical-proof':review['historicalProofSha256']='0'*64
    elif change=='corrected-proof':review['correctedProofSha256']='0'*64
    elif change=='owner':review['ownerApproval']=''
    if change!='missing':self.save(review,path,compiled)
    if change=='tamper':path.write_text('{}')
    with self.assertRaises(ValueError):packaging.native_pin_inputs(values[8],values[0],compiled)
 def test_unreviewed_origin_hash_signer_or_publisher_remains_rejected(self):
  for field in ['buildInput','buildSha256','signer','publisher']:
   with self.subTest(field=field),tempfile.TemporaryDirectory() as folder:
    values,review,receipt=self.fixture(Path(folder));pair=values[5]['pairs'][0]
    if field=='buildInput':pair[field]=str(Path(folder)/'unapproved.dll')
    elif field=='buildSha256':pair[field]='0'*64
    elif field=='signer':pair['buildAuthenticode']['Thumbprint']='unapproved-certificate'
    else:pair['buildAuthenticode']['Subject']='Another publisher'
    lineage.RepeatPinLineage().save(values[5],values[6],values[7])
    review['correctedProofSha256']=values[7]['nativeInputPinSha256']
    self.save(review,receipt,values[7])
    with self.assertRaises(ValueError):packaging.native_pin_inputs(values[8],values[0],values[7])

if __name__=='__main__':unittest.main()
