"""Agent file search (owner evidence 12_file_exists_but_agent_said_not_found)."""
import unittest

from agent_mcp import filename_matches, name_terms

DOWNLOADS = [
    'SELF_LEARNING_Alex_Doe_Final.pdf',
    'Self-Learning_Logbook_Alex_Doe_101_TY.pdf',
    'SELF_LEARNING_Alex_Doe_Final_Updated.docx',
    'Ramakant_Shrivastava_SL_Activity_Final.pdf',
    'Smart_Attendance_Presentation.pptx',
    'signature_chat_dark.png',
]


class FileNameSearchTests(unittest.TestCase):
    def test_self_learning_finds_both_pdfs_case_and_separator_insensitive(self):
        paths = [m['path'] for m in filename_matches('self learning', DOWNLOADS)]
        self.assertIn('SELF_LEARNING_Alex_Doe_Final.pdf', paths)
        self.assertIn('Self-Learning_Logbook_Alex_Doe_101_TY.pdf', paths)
        self.assertNotIn('Smart_Attendance_Presentation.pptx', paths)

    def test_extension_word_narrows_to_pdfs(self):
        paths = [m['path'] for m in filename_matches('self learning pdf', DOWNLOADS)]
        self.assertEqual(sorted(paths), sorted(['SELF_LEARNING_Alex_Doe_Final.pdf', 'Self-Learning_Logbook_Alex_Doe_101_TY.pdf']))

    def test_natural_phrasing_and_joined_words(self):
        self.assertTrue(filename_matches('a pdf about self learning', DOWNLOADS))
        self.assertTrue(filename_matches('selflearning', DOWNLOADS))
        self.assertEqual(filename_matches('quantum chromodynamics', DOWNLOADS), [])

    def test_name_terms_normalization(self):
        self.assertEqual(name_terms('SELF_LEARNING-Final.v2 pdf'), ['self', 'learning', 'final', 'v2', 'pdf'])


if __name__ == '__main__':
    unittest.main()
