import tempfile,unittest
from pathlib import Path
from agent_mcp import WorkspaceTools
from agent_workspace import WorkspaceAccess
from agent_permissions import GrantAuthority

class LineRangeTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.access=WorkspaceAccess(self.root);self.addCleanup(self.access.close)
  self.tools=WorkspaceTools(self.access,GrantAuthority(b'x'*32))
  (self.root/'example.txt').write_bytes(b'one\ntwo\nthree\nfour\n')
 def test_count_without_start_is_respected(self):
  r=self.tools.call('read_local_file',{'path':'example.txt','line_count':'2'})
  self.assertEqual(r['text'],'one\ntwo\n');self.assertTrue(r['scoped_range']);self.assertEqual(r['end_line'],2)
 def test_bad_ranges_never_fall_back_to_full_file(self):
  for extra in [{'start_line':'ten'},{'start_line':'0'},{'start_line':'-1'},{'line_count':'2.5'},{'line_count':'0'},{'line_count':'501'}]:
   with self.subTest(extra=extra),self.assertRaises(ValueError):self.tools.call('read_local_file',{'path':'example.txt',**extra})
 def test_long_requested_range_is_bounded_and_reports_truncation(self):
  full=('x'*4000+'\n')*10;(self.root/'long.txt').write_bytes(full.encode('utf-8'))
  r=self.tools.call('read_local_file',{'path':'long.txt','start_line':'1','line_count':'10'})
  self.assertEqual(r['text'],full[:16000]);self.assertTrue(r['truncated']);self.assertEqual(r['end_line'],4)
 def test_range_past_eof_has_no_invented_end_line(self):
  r=self.tools.call('read_local_file',{'path':'example.txt','start_line':'30','line_count':'2'})
  self.assertEqual(r['text'],'');self.assertIsNone(r['end_line']);self.assertEqual(r['total_lines'],4)
 def test_normal_explicit_range_and_plain_read_remain_correct(self):
  r=self.tools.call('read_local_file',{'path':'example.txt','start_line':'2','line_count':'2'});self.assertEqual(r['text'],'two\nthree\n');self.assertFalse(r['truncated'])
  self.assertEqual(self.tools.call('read_local_file',{'path':'example.txt'})['text'],'one\ntwo\nthree\nfour\n')
 def test_original_crlf_is_preserved(self):
  (self.root/'windows.txt').write_bytes(b'first\r\nsecond\r\nthird\r\n')
  r=self.tools.call('read_local_file',{'path':'windows.txt','start_line':'2','line_count':'1'})
  self.assertEqual(r['text'],'second\r\n');self.assertEqual(r['end_line'],2)

if __name__=='__main__':unittest.main()
