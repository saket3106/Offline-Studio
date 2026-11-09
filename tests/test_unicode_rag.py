"""Unicode retrieval and page evidence, using only authored document fixtures."""
import re
import unittest
from rag_engine import BM25Index, DocumentChunk, _tokenize, prepare_document_context


class UnicodeRetrievalTests(unittest.TestCase):
    def index(self):
        index = BM25Index()
        index.index_chunks([
            DocumentChunk('english', 'notes.pdf', 0, 'Python get_user_id HTTPServer v2 API_123', {'page': 1}),
            DocumentChunk('hindi', 'notes.pdf', 1, 'स्थानीय स्मृति और जानकारी सुरक्षित रहती है', {'page': 2}),
            DocumentChunk('arabic', 'notes.pdf', 2, 'الذاكرة المحلية تحفظ البيانات ١٢٣', {'page': 3}),
            DocumentChunk('chinese', 'notes.pdf', 3, '本地记忆 数据安全', {'page': 4}),
            DocumentChunk('accent', 'notes.pdf', 4, 'Café naïve Straße', {'page': 5}),
        ])
        return index

    def test_multilingual_queries_rank_matching_original_evidence(self):
        for query, expected in [('स्मृति', 'hindi'), ('الذاكرة', 'arabic'), ('١٢٣', 'arabic'),
                                ('本地记忆', 'chinese'), ('STRASSE', 'accent')]:
            with self.subTest(query=query):
                found = self.index().search(query, 1)
                self.assertEqual([chunk.chunk_id for chunk, _ in found], [expected])
                self.assertGreater(found[0][1], 0)

    def test_ascii_english_and_identifier_tokenization_stays_compatible(self):
        for text in ['Python HTTPServer v2', 'foo.bar foo-bar C++ x = 42', 'CASE CamelCase A 9']:
            self.assertEqual(_tokenize(text), re.findall(r'\b[a-z0-9]{2,}\b', text.lower()))
        self.assertEqual(_tokenize('get_user_id API_123'), ['get', 'user', 'id', 'api', '123'])
        for query in ['get_user_id', 'HTTPServer', 'API_123']:
            self.assertEqual(self.index().search(query, 1)[0][0].chunk_id, 'english')

    def test_canonical_and_compatibility_forms_match(self):
        self.assertEqual(_tokenize('Cafe\u0301'), _tokenize('Café'))
        self.assertEqual(_tokenize('ＡＰＩ１２３'), _tokenize('API123'))
        self.assertEqual(self.index().search('Cafe\u0301', 1)[0][0].chunk_id, 'accent')

    def test_unusable_and_unrelated_queries_never_return_initial_chunks(self):
        for query in ['', '  ', '!!! ___', '🦊', '\u0301\u0302', 'unrelatedquasar']:
            with self.subTest(query=query): self.assertEqual(self.index().search(query), [])

    def test_empty_index_and_zero_limit_have_no_results(self):
        self.assertEqual(BM25Index().search('स्मृति'), [])
        self.assertEqual(self.index().search('Python', 0), [])

    def test_context_keeps_original_text_source_and_physical_page(self):
        pages = ['Unrelated English cover.', 'स्थानीय स्मृति सुरक्षित रहती है।', 'الذاكرة المحلية تحفظ البيانات']
        text = '\n'.join(pages); cursor = 0; page_map = []
        for number, body in enumerate(pages, 1):
            page_map.append({'page': number, 'start': cursor, 'end': cursor+len(body)})
            cursor += len(body)+1
        metadata = {'pages': 3, 'page_map': page_map}; telemetry = {}
        context = prepare_document_context(text, 'स्मृति', 'authored.pdf', metadata=metadata, telemetry=telemetry)
        self.assertIn('PDF page 2', context)
        self.assertIn('स्थानीय स्मृति सुरक्षित रहती है।', context)
        self.assertIn('Source: authored.pdf', context)
        self.assertNotIn('Unrelated English cover.', context)
        self.assertIn('UNTRUSTED EXTERNAL DATA', context)
        self.assertLessEqual(len(context), 5000)
        self.assertEqual(telemetry['retrieved_chunks'], 1)

    def test_empty_context_query_does_not_invent_overview_matches(self):
        telemetry = {}
        context = prepare_document_context('summary overview introduction key points private fact', '', telemetry=telemetry)
        self.assertEqual(context, '')
        self.assertEqual(telemetry['retrieved_chunks'], 0)


if __name__ == '__main__': unittest.main()
