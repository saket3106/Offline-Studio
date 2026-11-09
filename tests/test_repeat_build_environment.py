"""Repeat-build search origins with synthetic identity-checked files, never loaded."""
from pathlib import Path
import os,tempfile,unittest
from unittest.mock import patch
import in_place_packaging as p

class RepeatEnvironmentTests(unittest.TestCase):
 def fixture(self,root):
  install=root/'Application';base=root/'python';sdk=root/'sdk/Scripts';crt=root/'crt';windows=root/'Windows'
  for d in (install,base/'DLLs',sdk,crt,windows/'System32'):d.mkdir(parents=True,exist_ok=True)
  (install/'Offline GPT.exe').write_bytes(b'accepted exe fixture');python=sdk/'python.exe';python.write_bytes(b'fixture only')
  entries=[];pins=[]
  for name in ('libssl-3-x64.dll','libcrypto-3-x64.dll','ucrtbase.dll'):
   installed=install/name;installed.write_bytes(b'original '+name.encode());source=(crt if name=='ucrtbase.dll' else base/'DLLs')/name
   source.write_bytes(installed.read_bytes() if name=='ucrtbase.dll' else b'reviewed signing variant '+name.encode())
   entries.append({'name':name,'input':str(source if name=='ucrtbase.dll' else installed),'inputSha256':p.digest(installed)})
   if name!='ucrtbase.dll':pins.append({'destination':name,'buildInput':str(source),'buildSha256':p.digest(source),'installedInput':str(installed),'installedSha256':p.digest(installed)})
  approved={'status':'PASS','installedExeSha256':'historical baseline','entries':entries}
  compiled={'exeSha256':p.digest(install/'Offline GPT.exe'),'compiledCanonicalModules':['app'],'compiledScripts':['app']}
  return install,base,python,windows,approved,compiled,pins
 def test_repeat_uses_verified_original_sdk_search_and_installed_payload(self):
  with tempfile.TemporaryDirectory() as temp:
   install,base,sdk,windows,approved,compiled,pins=self.fixture(Path(temp))
   with patch.object(p,'native_pin_inputs',return_value=pins):env,receipt=p.controlled_build_environment(approved,install,sdk,base,windows,{},compiled)
   self.assertEqual(env['PATH'].split(os.pathsep)[0],str(base/'DLLs'))
   self.assertEqual(next(x for x in receipt['pins'] if x['name']=='libssl-3-x64.dll')['sha256'],pins[0]['buildSha256'])
 def test_changed_sdk_or_installed_original_is_rejected(self):
  for key in ('buildInput','installedInput'):
   with self.subTest(key=key),tempfile.TemporaryDirectory() as temp:
    install,base,sdk,windows,approved,compiled,pins=self.fixture(Path(temp));Path(pins[0][key]).write_bytes(b'changed')
    with patch.object(p,'native_pin_inputs',return_value=pins),self.assertRaises(ValueError):p.controlled_build_environment(approved,install,sdk,base,windows,{},compiled)

if __name__=='__main__':unittest.main()
