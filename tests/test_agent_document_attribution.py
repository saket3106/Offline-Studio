"""Authorized source names, physical pages and honest document coverage."""
import hashlib,tempfile,unittest
from pathlib import Path
import pymupdf
from agent_mcp import WorkspaceTools
from agent_workspace import WorkspaceAccess
from agent_permissions import GrantAuthority

class DocumentAttributionTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  self.access=WorkspaceAccess(self.root);self.addCleanup(self.access.close);self.tools=WorkspaceTools(self.access,GrantAuthority(b'x'*32))
 def test_pdf_source_and_physical_page_map_survive_temporary_extraction(self):
  folder=self.root/'reports';folder.mkdir();path=folder/'quarterly.pdf';doc=pymupdf.open()
  for value in ['ALPHA page one','BETA page two']:doc.new_page().insert_text((72,72),value)
  doc.save(path);doc.close();result=self.tools.call('extract_pdf_text',{'path':'reports/quarterly.pdf'})
  self.assertEqual(result['source'],'reports/quarterly.pdf');self.assertEqual(result['metadata']['filename'],'quarterly.pdf')
  self.assertEqual(result['metadata']['pages'],2);self.assertEqual([p['page'] for p in result['metadata']['page_map']],[1,2])
  for page,word in zip(result['metadata']['page_map'],['ALPHA','BETA']):self.assertIn(word,result['text'][page['start']:page['end']])
  self.assertTrue(result['coverage_complete']);self.assertFalse(result['omitted']);self.assertEqual(result['sha256'],hashlib.sha256(path.read_bytes()).hexdigest())
 def test_long_docx_reports_omission_and_preserves_original(self):
  from docx import Document
  path=self.root/'notes.docx';doc=Document();doc.add_paragraph('Evidence '*1800);doc.save(path);before=path.read_bytes()
  result=self.tools.call('read_docx',{'path':'notes.docx'})
  self.assertEqual(result['metadata']['filename'],'notes.docx');self.assertEqual(len(result['text']),12000)
  self.assertTrue(result['truncated']);self.assertTrue(result['omitted']);self.assertFalse(result['coverage_complete']);self.assertEqual(path.read_bytes(),before)
 def test_scanned_page_is_not_claimed_as_complete_text_or_ocr(self):
  path=self.root/'illustration.pdf';doc=pymupdf.open();page=doc.new_page();page.draw_rect(pymupdf.Rect(40,40,120,120));doc.save(path);doc.close()
  result=self.tools.call('extract_pdf_text',{'path':'illustration.pdf'})
  self.assertEqual(result['scannedPagesRequiringOcr'],[1]);self.assertFalse(result['ocrPerformed']);self.assertTrue(result['omitted']);self.assertFalse(result['coverage_complete'])

if __name__=='__main__':unittest.main()
