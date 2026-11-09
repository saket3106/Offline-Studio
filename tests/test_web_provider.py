"""Keyless 'web' discovery: DuckDuckGo Lite organic results, Bing News RSS, Wikipedia, and honest skips.

Measured 2026-11-08 (live, through SafeWebClient with robots on): "Nvidia RTX 5090 price" returned a price
tracker, three current news articles and the Wikipedia series page; html.duckduckgo.com answered with an
"anomaly" human check, which is reported and skipped, never worked around.
"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import research_network
from research_network import SearchProviders, FRESH, ResearchError
from intelligence_engine import needs_web, compact_query, fan_out, citation_context, weather_place

LITE = """<table><tr><td><a rel="nofollow" href="/l/?uddg=https%3A%2F%2Fduckduckgo.com%2Fy.js%3Fad_domain%3Damazon.com" class='result-link'>Shop now - Ad</a></td></tr>
<tr><td class='result-snippet'>Ad text</td></tr>
<tr><td><a rel="nofollow" href="/l/?uddg=https%3A%2F%2Fgcc.gnu.org%2F&amp;rut=abc" class='result-link'>GCC, the GNU Compiler Collection</a></td></tr>
<tr><td class='result-snippet'>The GNU <b>Compiler</b> Collection includes front ends for C, C++.</td></tr>
<tr><td><a rel="nofollow" href="/l/?uddg=https%3A%2F%2Fclang.llvm.org%2F&amp;rut=def" class='result-link'>Clang C Language Family Frontend</a></td></tr>
<tr><td class='result-snippet'>Clang is a C, C++ and Objective-C compiler.</td></tr></table>"""
RSS = """<rss><channel><item><title>Who won IPL 2026? Final result</title><link>http://www.bing.com/news/apiclick.aspx?ref=x&amp;url=https%3a%2f%2fwww.example-news.com%2fipl-final&amp;c=1</link>
<description>RCB beat GT in the final &amp; lifted the trophy.</description><pubDate>Sun, 31 May 2026 18:00:00 GMT</pubDate></item></channel></rss>"""


class FakeClient:
    def __init__(self, pages): self.pages = pages; self.urls = []
    def check(self): pass
    def fetch(self, url, headers=None, limit=None, robots=True):
        self.urls.append((url, robots))
        for key, (status, body, kind) in self.pages.items():
            if key in url: return {'status': status, 'headers': {'content-type': kind}, 'body': body.encode(), 'url': url, 'sha256': 'x'}
        raise ResearchError('unexpected ' + url)


WIKI = '{"query":{"search":[{"pageid":7,"title":"Compiler","snippet":"A compiler translates code."}]}}'


class WebProviderTests(unittest.TestCase):
    def setUp(self): research_network._DDG_PAUSED_UNTIL[0] = 0.0
    tearDown = setUp
    def provider(self, pages): return SearchProviders(FakeClient(pages), {'research_provider': 'web', 'research_max_queries': 2})

    def test_human_check_pauses_duckduckgo(self):
        pages = {'lite.duckduckgo.com': (200, '<html>anomaly captcha</html>', 'text/html'), 'wikipedia.org': (200, WIKI, 'application/json')}
        self.provider(pages).search('best C++ compilers', limit=4)
        again = self.provider(pages)
        again.search('rust compilers', limit=4)
        self.assertFalse(any('duckduckgo' in url for url, _ in again.client.urls))
        self.assertTrue(any('paused' in e for e in again.last_meta['errors']))

    def test_weather_questions_read_a_live_forecast(self):
        geo = '{"results":[{"name":"Pune","latitude":18.51957,"longitude":73.85535,"admin1":"Maharashtra","country":"India","timezone":"Asia/Kolkata"}]}'
        step = lambda h, t, sym: '{"time":"2026-11-08T%02d:00:00Z","data":{"instant":{"details":{"air_temperature":%s,"relative_humidity":50,"wind_speed":2}},"next_1_hours":{"summary":{"symbol_code":"%s"},"details":{"precipitation_amount":0}}}}' % (h, t, sym)
        met = '{"properties":{"timeseries":[%s]}}' % ','.join(step(h, 20 + h % 12, 'partlycloudy_day' if h else 'clearsky_night') for h in range(24))
        p = self.provider({'geocoding-api.open-meteo.com': (200, geo, 'application/json'), 'api.met.no': (200, met, 'application/json')})
        rows = p.search('Pune', engines=['weather'])
        self.assertEqual(rows[0]['provider'], 'weather')
        self.assertIn('lat=18.52&lon=73.855', rows[0]['url'])
        page = p.fetch_result(rows[0])
        self.assertIn('Now: 20 °C, clear sky', page['text'])
        self.assertIn('partly cloudy', page['text'])
        self.assertIn('Sun 08 Nov 05:30', page['text'])  # local time (IST)
        self.assertIn('low 20 °C, high 31 °C', page['text'])
        self.assertIn('MET Norway', page['license'])
        self.assertTrue(all(robots for _, robots in p.client.urls))
        self.assertEqual([weather_place(q) for q in ['weather in Pune today', 'Mumbai temperature tomorrow', 'what is the weather in New York right now?', 'explain how weather forms', 'weather today']],
                         ['Pune', 'Mumbai', 'New York', '', ''])
        self.assertEqual(fan_out('weather in Pune today', 'weather Pune today', {'research_provider': 'web', 'research_max_queries': 3})[0], ('Pune', ['weather']))

    def test_fan_out_covers_broad_and_current_questions(self):
        cfg = {'research_provider': 'web', 'research_max_queries': 3}
        broad = fan_out('tell me about LLM models', 'LLM models', cfg)
        self.assertEqual([q for q, _ in broad][:2], ['LLM models', 'list of LLM models'])
        self.assertEqual(broad[1][1], ['wikimedia'])
        self.assertEqual(len(broad), 3)
        self.assertEqual(fan_out('who won IPL 2026', 'IPL 2026 winner', cfg), [('IPL 2026 winner', None)])
        self.assertEqual(fan_out('ISRO latest news', 'ISRO', cfg), [('ISRO', None), ('ISRO latest', ['bingnews'])])
        self.assertEqual(fan_out('who is the CEO of OpenAI', 'CEO OpenAI', cfg), [('CEO OpenAI', None), ('CEO OpenAI', ['bingnews'])])
        self.assertEqual(len(fan_out('x y', 'x y', dict(cfg, research_max_queries=1))), 1)
        self.assertEqual(fan_out('orchid', 'orchid', {'research_provider': 'public', 'research_max_queries': 3}), [('orchid', None)])

    def test_evidence_budget_gives_each_page_more_room(self):
        sources = [{'id': f'K{i:016d}', 'url': f'https://e{i}.org/', 'title': f'T{i}', 'fetchStatus': 'FETCHED', 'excerpt': 'w' * 3000} for i in range(4)]
        sources.append({'id': 'K' + '9' * 16, 'url': 'https://n.org/', 'title': 'N', 'fetchStatus': 'SEARCH_RESULT_SNIPPET', 'excerpt': 's' * 900})
        text, used = citation_context(sources, [], budget=5200)
        self.assertEqual(len(used), 5)
        self.assertIn('w' * 1000, text)
        self.assertNotIn('s' * 401, text)
        self.assertIn('search overview', text)
        self.assertLess(len(text), 7600)

    def test_organic_results_without_ads_and_robots_checked(self):
        p = self.provider({'lite.duckduckgo.com': (200, LITE, 'text/html'), 'wikipedia.org': (200, WIKI, 'application/json')})
        rows = p.search('best C++ compilers', limit=4)
        self.assertEqual([r['url'] for r in rows], ['https://gcc.gnu.org/', 'https://en.wikipedia.org/wiki/Compiler', 'https://clang.llvm.org/'])
        self.assertIn('C++', rows[0]['snippet'])
        self.assertTrue(all(robots for url, robots in p.client.urls if 'duckduckgo' in url))
        self.assertFalse(any('bing.com' in url for url, _ in p.client.urls), 'timeless question: no news query')

    def test_current_questions_add_news_with_publisher_url(self):
        p = self.provider({'lite.duckduckgo.com': (200, LITE, 'text/html'), 'bing.com/news': (200, RSS, 'application/xml'), 'wikipedia.org': (200, WIKI, 'application/json')})
        rows = p.search('who won IPL 2026', limit=4)
        news = [r for r in rows if r['provider'] == 'bingnews']
        self.assertEqual(news[0]['url'], 'https://www.example-news.com/ipl-final')
        self.assertIn('&', news[0]['snippet'])
        self.assertEqual(p.query_count, 3)

    def test_human_check_is_skipped_and_news_still_answers(self):
        p = self.provider({'lite.duckduckgo.com': (200, '<html>anomaly detected, complete the captcha</html>', 'text/html'),
                           'bing.com/news': (200, RSS, 'application/xml'), 'wikipedia.org': (200, WIKI, 'application/json')})
        rows = p.search('best C++ compilers', limit=4)
        self.assertTrue(any('human check' in e for e in p.last_meta['errors']))
        self.assertEqual({r['provider'] for r in rows}, {'bingnews', 'wikimedia'})

    def test_fresh_and_hybrid_routing(self):
        # Owner rule 2026-11-09: Automatic researches only when asked (or live weather / a pasted link); Always search researches all.
        for q in ['what are the best open source LLM models right now', 'top 5 phones under 30000', 'who won IPL 2026', 'how much does an iPhone 17 cost', 'who is the current prime minister of Japan', 'latest Nvidia drivers']:
            self.assertFalse(needs_web(q, 'hybrid'), q)
            self.assertTrue(needs_web(q, 'web'), q)
            self.assertTrue(needs_web('search the web: ' + q, 'hybrid'), q)
        self.assertTrue(needs_web('weather in Pune today', 'hybrid'))
        for q in ['explain what is a LLM model in 500 words', 'write a poem about rain', 'what is recursion', 'tell me a joke']:
            self.assertFalse(needs_web(q, 'hybrid'), q)
        self.assertTrue(needs_web('write a poem about rain', 'web'))
        self.assertFalse(FRESH.search('best C++ compilers'))

    def test_queries_keep_the_subject(self):
        self.assertEqual(compact_query('gather all the information available on web about LLM models and tell me here.'), 'LLM models')
        self.assertEqual(compact_query('search the web for best C++ compilers'), 'best C++ compilers')
        self.assertEqual(compact_query('Who is the prime minister of India?'), 'prime minister India')
        self.assertEqual(compact_query('who won IPL 2026'), 'IPL 2026 winner')
        self.assertEqual(compact_query('RTX 5090 price in India'), 'RTX 5090 price India')


if __name__ == '__main__':
    unittest.main()
