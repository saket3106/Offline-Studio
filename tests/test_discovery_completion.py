"""Provider schema/budget/metadata tests. Real public API evidence is separate."""
import hashlib,json,unittest
from urllib.parse import parse_qs,urlsplit
from research_network import SearchProviders,ResearchError,NetworkGrant,SafeWebClient

class Client:
    def __init__(self,payloads):self.payloads=iter(payloads);self.requests=[]
    def check(self):pass
    def fetch(self,url,**kwargs):
        self.requests.append((url,kwargs));payload=next(self.payloads)
        if isinstance(payload,BaseException):raise payload
        if isinstance(payload,tuple):content_type,body=payload
        else:content_type='application/json';body=json.dumps(payload).encode()
        return {'url':url,'body':body,'headers':{'content-type':content_type},'sha256':hashlib.sha256(body).hexdigest()}

class DiscoveryTests(unittest.TestCase):
    def provider(self,name,payloads,**config):
        client=Client(payloads);return SearchProviders(client,{'research_provider':name,'research_max_queries':4,**config}),client
    def test_none_does_not_request_network(self):
        p,c=self.provider('none',[])
        with self.assertRaisesRegex(ResearchError,'No search provider'):p.search('example')
        self.assertEqual([],c.requests)
    def test_offline_probe_is_denied_before_dns(self):
        p=SearchProviders(SafeWebClient(NetworkGrant('denied')),{'research_provider':'public'})
        with self.assertRaises(PermissionError):p.probe()
    def test_searxng_page_json_category_and_dedup(self):
        p,c=self.provider('searxng',[{'results':[{'url':'https://example.org/a#x','title':'A'},{'url':'https://example.org/a#y','title':'Duplicate'},{'url':'http://127.0.0.1/private'},{'url':'file:///private'}]}],research_endpoint='https://search.example/search')
        result=p.search('public query',page=2,limit=4);self.assertEqual(1,len(result));params=parse_qs(urlsplit(c.requests[0][0]).query);self.assertEqual(['2'],params['pageno']);self.assertEqual(['json'],params['format']);self.assertEqual('DISCOVERED_NOT_READ',result[0]['status']);self.assertFalse(c.requests[0][1]['robots'])
    def test_searxng_html_and_invalid_json_have_actionable_error(self):
        p,_=self.provider('searxng',[('text/html',b'<html>JSON disabled</html>')],research_endpoint='https://search.example/')
        result=p.probe();self.assertEqual('UNAVAILABLE',result['status']);self.assertFalse(result['jsonCapable']);self.assertIn('enable JSON',result['error'])
        p,_=self.provider('searxng',[('application/json',b'{broken')],research_endpoint='https://search.example/')
        with self.assertRaisesRegex(ResearchError,'malformed JSON'):p.search('test')
    def test_brave_key_header_never_in_url_or_probe_output(self):
        p,c=self.provider('brave',[{'web':{'results':[{'url':'https://example.org/result','title':'Result','description':'Found'}]}}]);p.secret='SECRET-fixture';report=p.probe('test')
        self.assertEqual('SECRET-fixture',c.requests[0][1]['headers']['X-Subscription-Token']);self.assertNotIn('SECRET-fixture',c.requests[0][0]);self.assertNotIn('SECRET-fixture',json.dumps(report));self.assertTrue(report['jsonCapable'])
    def test_missing_brave_key_and_api_error_do_not_replay(self):
        p,c=self.provider('brave',[])
        with self.assertRaisesRegex(ResearchError,'API key'):p.search('query')
        self.assertEqual([],c.requests)
        p,c=self.provider('brave',[{'error':{'message':'Do not leak raw API response'}}]);p.secret='key'
        with self.assertRaisesRegex(ResearchError,'API error'):p.search('query')
        self.assertEqual(1,len(c.requests))
    def test_public_composite_interleaves_and_enforces_total_budget(self):
        wiki={'query':{'search':[{'pageid':1,'title':'Encyclopedia A'},{'pageid':2,'title':'Encyclopedia B'}]}};cross={'message':{'items':[{'DOI':'10.1/example','title':['Scholarly A']}]}}
        p,c=self.provider('public',[wiki,cross],research_max_queries=2);rows=p.search('topic',limit=2)
        self.assertEqual(['wikimedia','crossref','wikimedia'],[r['provider'] for r in rows]);self.assertEqual(2,p.query_count);self.assertEqual(2,p.last_meta['queriesSent']);self.assertIn('not internet-wide',p.last_meta['breadth']);self.assertEqual([],p.search('other topic'));self.assertEqual(2,len(c.requests))
    def test_public_partial_error_retains_success_and_reports_scope(self):
        p,_=self.provider('public',[{'query':{'search':[{'pageid':1,'title':'Evidence'}]}},ResearchError('Website returned HTTP 429')]);rows=p.search('topic')
        self.assertEqual(1,len(rows));self.assertIn('429',p.last_meta['errors'][0]);self.assertEqual(2,p.query_count)
    def test_wikipedia_read_has_actual_response_revision_and_no_full_article_claim(self):
        p,c=self.provider('wikimedia',[{'query':{'search':[{'pageid':7,'title':'Actual article','snippet':'<b>Original</b> snippet','timestamp':'2026-11-01'}]}},{'query':{'pages':[{'pageid':7,'title':'Actual article','canonicalurl':'https://en.wikipedia.org/wiki/Actual_article','extract':'Actual factual source text. '*8,'revisions':[{'revid':91,'timestamp':'2026-11-01T00:00:00Z'}],'extlinks':[{'url':'https://manufacturer.example/specs'},{'url':'http://localhost/private'}]}]}}])
        row=p.search('actual')[0];source=p.fetch_result(row);self.assertEqual('FETCHED',source['fetchStatus']);self.assertEqual('encyclopedia_excerpt',source['sourceType']);self.assertEqual(91,source['revisionId']);self.assertEqual(64,len(source['contentFingerprint']));self.assertEqual(64,len(source['responseFingerprint']));self.assertIn('1,200',source['coverage']);self.assertEqual(['https://manufacturer.example/specs'],source['externalLinks']);self.assertEqual(1,p.query_count);self.assertEqual(2,len(c.requests))
    def test_wikipedia_canonical_host_change_is_rejected(self):
        p,_=self.provider('wikimedia',[{'query':{'pages':[{'pageid':8,'canonicalurl':'https://evil.example/','extract':'text '*40}]}}])
        with self.assertRaisesRegex(ResearchError,'canonical host changed'):p.fetch_result({'provider':'wikimedia','metadataId':'8','url':'https://en.wikipedia.org/wiki/Test'})
    def test_wikipedia_returned_id_must_match_observed_identity(self):
        p,_=self.provider('wikimedia',[{'query':{'pages':[{'pageid':9,'canonicalurl':'https://en.wikipedia.org/wiki/Other','extract':'text '*40}]}}])
        with self.assertRaisesRegex(ResearchError,'page identity changed'):p.fetch_result({'provider':'wikimedia','metadataId':'8','url':'https://en.wikipedia.org/wiki/Test'})
    def test_crossref_reads_only_matching_metadata_identity(self):
        p,c=self.provider('crossref',[{'message':{'DOI':'10.123/a','title':['An article'],'abstract':'<jats:p>Observed metadata abstract.</jats:p>','published':{'date-parts':[[2026,10,1]]}}}]);row={'provider':'crossref','metadataId':'10.123/a','url':'https://doi.org/10.123/a'};source=p.fetch_result(row)
        self.assertEqual('scholarly_metadata',source['sourceType']);self.assertEqual('2026-10-01',source['published']);self.assertIn('full text was not read',source['coverage']);self.assertIn('10.123%2Fa',c.requests[0][0]);self.assertNotIn('<jats',source['text'])
    def test_commons_returns_real_rights_metadata_and_no_image_bytes(self):
        payload={'query':{'pages':[{'pageid':17,'title':'File:Vehicle.png','index':1,'imageinfo':[{'url':'https://upload.wikimedia.org/a.png','thumburl':'https://upload.wikimedia.org/thumb.png','descriptionurl':'https://commons.wikimedia.org/wiki/File:Vehicle.png','mime':'image/png','width':4000,'height':2000,'thumbwidth':1000,'thumbheight':500,'extmetadata':{'LicenseShortName':{'value':'CC BY-SA 4.0'},'LicenseUrl':{'value':'https://creativecommons.org/licenses/by-sa/4.0'},'Artist':{'value':'<a href="https://example.org">Test Artist</a>'},'AttributionRequired':{'value':'true'},'ImageDescription':{'value':'A known motorcycle'}}}]}]}}
        p,c=self.provider('commons',[payload]);rows=p.search('Royal Enfield Hunter 350',images=True);self.assertEqual(1,len(rows));self.assertEqual('DISCOVERED_NOT_DOWNLOADED',rows[0]['status']);self.assertEqual('CC BY-SA 4.0',rows[0]['license']);self.assertEqual('Test Artist',rows[0]['artist']);self.assertTrue(rows[0]['attributionRequired']);self.assertEqual(1,len(c.requests));self.assertIn('"Royal Enfield Hunter 350"',parse_qs(urlsplit(c.requests[0][0]).query)['gsrsearch'][0]);self.assertFalse(any('upload.wikimedia' in url for url,_ in c.requests))
    def test_commons_active_and_private_formats_are_excluded(self):
        p,_=self.provider('commons',[{'query':{'pages':[{'pageid':1,'imageinfo':[{'mime':'image/svg+xml'}]},{'pageid':2,'imageinfo':[{'mime':'image/png','url':'http://127.0.0.1/x.png','descriptionurl':'https://commons.wikimedia.org/wiki/File:X'}]}]}}]);self.assertEqual([],p.search('test',images=True))

if __name__=='__main__':unittest.main()
