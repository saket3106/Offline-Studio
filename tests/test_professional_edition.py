"""Real Qt folder dialog boundaries and source presentation contract, no AI."""
import os,json,tempfile,unittest,subprocess,shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication,QWidget,QFileDialog
from PySide6.QtCore import QTimer
from agent_desktop import DesktopAgentController
S=Path(__file__).resolve().parents[1]
class ProfessionalEditionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.qt=QApplication.instance() or QApplication([])
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.window=QWidget();self.window.resize(1200,800)
  self.bridge=SimpleNamespace(window=self.window,backend=SimpleNamespace(busy=False));self.controller=DesktopAgentController.__new__(DesktopAgentController);self.controller.bridge=self.bridge;self.controller.backend=self.bridge.backend;self.controller.root='';self.controller.worker=None
  self.addCleanup(self.window.close)
 def test_folder_only_dialog_uses_real_navigation_and_screen_dimensions(self):
  d=self.controller.workspace_dialog();self.addCleanup(d.deleteLater)
  self.assertEqual(d.fileMode(),QFileDialog.FileMode.Directory);self.assertTrue(d.testOption(QFileDialog.Option.ShowDirsOnly));self.assertTrue(d.testOption(QFileDialog.Option.DontUseNativeDialog));self.assertTrue(d.isSizeGripEnabled())
  area=self.window.screen().availableGeometry();self.assertLessEqual(d.width(),area.width());self.assertLessEqual(d.height(),area.height());self.assertGreaterEqual(d.width(),min(640,area.width()-32));self.assertGreaterEqual(d.height(),min(420,area.height()-32))
  d.setDirectory(str(self.root));self.assertEqual(d.directory().absolutePath(),str(self.root).replace('\\','/'));d.resize(d.width()-20,d.height()-20);self.assertGreater(d.width(),0)
 def test_choosing_folder_never_grants_authorization(self):
  d=self.controller.workspace_dialog();d.setDirectory(str(self.root));self.controller.workspace_dialog=lambda:d;self.controller.authorize_workspace=Mock(side_effect=AssertionError('selection cannot authorize'))
  QTimer.singleShot(10,d.accept);result=self.controller.pick();self.assertTrue(result['requiresAuthorization']);self.assertEqual(Path(result['selectedWorkspace']),self.root);self.assertEqual(self.controller.root,'');self.controller.authorize_workspace.assert_not_called();d.deleteLater()
 def test_cancellation_preserves_existing_scope(self):
  self.controller.root=str(self.root);d=self.controller.workspace_dialog();self.controller.workspace_dialog=lambda:d;QTimer.singleShot(10,d.reject)
  self.assertTrue(self.controller.pick()['cancelled']);self.assertEqual(self.controller.root,str(self.root));d.deleteLater()
 def test_running_task_does_not_open_picker(self):
  self.controller.backend.busy=True;self.controller.workspace_dialog=Mock();self.assertFalse(self.controller.pick()['ok']);self.controller.workspace_dialog.assert_not_called()
 def test_previously_selected_location_used_without_reauthorizing(self):
  self.controller._last_workspace_location=str(self.root);d=self.controller.workspace_dialog();self.assertEqual(Path(d.directory().absolutePath()),self.root);self.assertEqual(self.controller.root,'');d.deleteLater()
 def test_backend_phase_mapping_is_not_timer_driven(self):
  node=shutil.which('node') or str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe');source=(S/'frontend-source/src/agent.jsx').read_text();start=source.index('export function agentPhase');end=source.index('\nexport function MCPServers',start);helper=source[start:end].replace('export ','')
  script=helper+"\nconst assert=require('node:assert/strict');for(const [state,expected] of Object.entries({IDLE:'Ready',PREPARING:'Planning',EXECUTING_TOOL:'Using tools',PROCESSING_RESULT:'Reviewing results',AWAITING_APPROVAL:'Needs permission',COMPLETED:'Completed',PARTIAL:'Partial',FAILED:'Failed',CANCELED:'Canceled'}))assert.equal(agentPhase(state),expected);console.log('9 phase checks');"
  r=subprocess.run([node,'-e',script],capture_output=True,text=True,timeout=10);self.assertEqual(r.returncode,0,r.stderr)
 def test_details_and_permissions_are_keyboard_accessible(self):
  source=(S/'frontend-source/src/agent.jsx').read_text();self.assertIn('<details className="agent-trace-container"',source);self.assertIn('<button type="button" className="trace-step-summary" aria-expanded=',source);self.assertIn('requiresAuthorization && result.selectedWorkspace',source);self.assertIn('Allow folder access',source);self.assertIn('if (!alive || event.type',source)
 def test_status_does_not_invent_selected_model_from_placeholder(self):
  self.controller.backend.current='chat';self.controller.backend.model='gpt-oss-20b'
  self.controller.backend.store=SimpleNamespace(get_chat_model=lambda _: '')
  self.controller.backend.engines=SimpleNamespace(cfg={'chat_backend':'bundled','gpt_oss_gguf':''},vision_model_status=lambda:{'visionAvailable':False})
  self.assertEqual(self.controller.status()['selectedModel'],'')
  self.controller.backend.engines.cfg['gpt_oss_gguf']='C:/Models/chosen.gguf';self.assertEqual(self.controller.status()['selectedModel'],'C:/Models/chosen.gguf')

if __name__=='__main__':unittest.main()
