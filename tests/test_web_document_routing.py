"""Remote source URLs must not trip the local attachment preflight."""
import unittest
from router import has_document_reference, route_request

class WebDocumentRoutingTests(unittest.TestCase):
    def test_public_source_urls_do_not_require_attachment(self):
        for url in ('https://www.sqlite.org/fts5.html', 'https://example.org/manual.pdf?q=report.docx', 'http://example.org/report.txt'):
            with self.subTest(url=url):
                text='State what this source provides: '+url
                self.assertFalse(has_document_reference(text))
                self.assertFalse(route_request(text)['missing_document'])

    def test_local_references_remain_required_beside_urls(self):
        for text in ('Compare my notes with https://example.org/a.html', 'Read attached PDF and https://example.org/b.pdf', 'Compare local-report.pdf with https://example.org/b.pdf', 'Read this document'):
            with self.subTest(text=text):
                self.assertTrue(has_document_reference(text))
                self.assertTrue(route_request(text)['missing_document'])

    def test_actual_attachment_retains_document_route(self):
        self.assertTrue(has_document_reference('https://example.org/a.html',has_document=True))
        self.assertFalse(route_request('Read this document',has_document=True)['missing_document'])

if __name__=='__main__':unittest.main()
