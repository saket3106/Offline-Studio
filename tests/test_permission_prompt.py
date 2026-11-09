"""The web-research permission prompt is raised on top and returns the clicked choice."""
import os, unittest
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget
from intelligence_host import ask_on_top
from intelligence_engine import needs_web


class PermissionPromptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.qt = QApplication.instance() or QApplication([])

    def answer(self, which):
        def click():
            box = next(w for w in QApplication.topLevelWidgets() if w.objectName() == 'studio-permission-dialog' and w.isVisible())
            self.assertTrue(box.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
            self.assertEqual(box.accessibleName(), 'Allow web research')
            box.button(which).click()
        QTimer.singleShot(50, click)

    def test_yes_and_no_are_reported(self):
        parent = QWidget(); self.addCleanup(parent.close)
        self.answer(QMessageBox.Yes); self.assertEqual(ask_on_top(parent, 'Allow web research', 'q'), QMessageBox.Yes)
        self.answer(QMessageBox.No); self.assertEqual(ask_on_top(parent, 'Allow web research', 'q'), QMessageBox.No)

    def test_always_allow_is_offered_and_reported(self):
        parent = QWidget(); self.addCleanup(parent.close)
        self.answer(QMessageBox.YesToAll); self.assertEqual(ask_on_top(parent, 'Allow web research', 'q', always=True), QMessageBox.YesToAll)
        self.answer(QMessageBox.Yes); self.assertEqual(ask_on_top(parent, 'Allow web research', 'q', always=True), QMessageBox.Yes)

    def test_hybrid_routes_explicit_internet_requests_to_research(self):
        # Owner rule 2026-11-09: the web only when the message asks for it.
        self.assertFalse(needs_web('gather all info about llm models', 'hybrid'))
        self.assertTrue(needs_web('gather all info about llm models from the web', 'hybrid'))
        self.assertTrue(needs_web('gather every information from internet and explain me properly what are llm models', 'hybrid'))
        self.assertFalse(needs_web('explain what is a LLM model in 500 words', 'hybrid'))
        self.assertFalse(needs_web('explain what is a LLM model in 500 words', 'offline'))


if __name__ == '__main__':
    unittest.main()
