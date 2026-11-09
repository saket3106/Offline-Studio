"""Permission-gated, bounded public-web retrieval. No model or browser dependency."""
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, urljoin, urlencode,quote,parse_qs
import hashlib,html,http.client,ipaddress,json,re,socket,ssl,threading,time


class ResearchError(RuntimeError):pass


@dataclass(frozen=True)
class NetworkGrant:
    request_id:str
    allowed:bool=False
    query_digest:str=''
    @classmethod
    def issue(cls,request_id,query):
        return cls(str(request_id),True,hashlib.sha256(str(query).encode()).hexdigest())
    def require(self):
        if not self.allowed:raise PermissionError('Strict Offline mode: external requests are disabled.')


def canonical_url(value):
    value=str(value).strip()
    if len(value)>4096 or re.search(r'[\x00-\x20\x7f\\]',value):raise ResearchError('Unsafe or oversized URL.')
    p=urlsplit(value)
    if p.scheme not in {'https','http'} or not p.hostname or p.username or p.password:raise ResearchError('Only credential-free HTTP(S) URLs are supported.')
    host=p.hostname.encode('idna').decode('ascii').lower().rstrip('.')
    if '%' in host or host in {'localhost','localhost.localdomain'} or host.endswith(('.localhost','.local','.internal')):raise ResearchError('Local/internal services are unavailable to research.')
    port=p.port or (443 if p.scheme=='https' else 80)
    if port not in {80,443}:raise ResearchError('Only public HTTP(S) service ports are supported.')
    authority=('['+host+']') if ':' in host else host
    if port!=(443 if p.scheme=='https' else 80):authority+=':'+str(port)
    return urlunsplit((p.scheme,authority,p.path or '/',p.query,''))


def public_addresses(host,port,resolver=socket.getaddrinfo):
    addresses=sorted({item[4][0] for item in resolver(host,port,type=socket.SOCK_STREAM)})
    if not addresses:raise ResearchError('The website did not resolve.')
    for address in addresses:
        ip=ipaddress.ip_address(address)
        embedded=[getattr(ip,'ipv4_mapped',None),getattr(ip,'sixtofour',None)]
        if getattr(ip,'teredo',None):embedded.extend(ip.teredo)
        if not ip.is_global or ip.is_multicast or any(item and not item.is_global for item in embedded):raise ResearchError('Research cannot access private, reserved or internal addresses.')
    return addresses


class RobotsPolicy:
    """Bounded RFC 9309 path rules; per-request cache, no scripts or new dependency.

    Longest matching rule wins; allow wins a tie. Matching agent groups merge.
    Unknown extensions are ignored except crawl-delay, which is handled conservatively.
    """
    def __init__(self,text):
        self.groups=[];agents=[];rules=[];delay=0;has_rules=False
        for line in text.lstrip('\ufeff').splitlines():
            if len(line)>2048 or line.count('*')>8:raise ResearchError('Robots policy exceeds bounded parser limits; source declined.')
            line=line.split('#',1)[0].strip()
            if ':' not in line:continue
            key,value=(part.strip() for part in line.split(':',1));key=key.lower()
            if key=='user-agent':
                if has_rules:self.groups.append((agents,rules,delay));agents=[];rules=[];delay=0;has_rules=False
                agents.append(value.casefold())
            elif key in {'allow','disallow'} and agents:
                has_rules=True
                if value.startswith('/'):
                    pattern=self.normalize(value);anchored=pattern.endswith('$');pattern=pattern[:-1] if anchored else pattern
                    rules.append((len(pattern.replace('*','')),key=='allow',pattern.split('*'),anchored))
            elif key=='crawl-delay' and agents:
                has_rules=True
                try:delay=max(delay,float(value))
                except ValueError:pass
        if agents:self.groups.append((agents,rules,delay))
    @staticmethod
    def normalize(value):
        value=quote(value,safe="/%*?$=&:@!+,;~-._()'")
        def percent(match):
            number=int(match.group()[1:],16);char=chr(number)
            return char if char.isascii() and (char.isalnum() or char in '-._~') else '%'+format(number,'02X')
        return re.sub(r'%[a-fA-F0-9]{2}',percent,value)
    def can_fetch(self,agent,url):
        product=agent.split('/',1)[0].casefold();selected=[g for g in self.groups if product in g[0]]
        if not selected:selected=[g for g in self.groups if '*' in g[0]]
        # A crawler that cannot honor a server's delay within its bounded
        # lifecycle declines the source instead of silently ignoring it.
        if any(group[2]>0 for group in selected):return False
        p=urlsplit(url);path=self.normalize((p.path or '/')+('?' +p.query if p.query else ''))
        matches=[(size,allow) for _,rules,_ in selected for size,allow,parts,anchor in rules if self.match(path,parts,anchor)]
        return max(matches)[1] if matches else True
    @staticmethod
    def match(path,parts,anchor):
        # Literal segment search avoids regex backtracking on hostile policies.
        if not path.startswith(parts[0]):return False
        if len(parts)==1:return path==parts[0] if anchor else True
        position=len(parts[0])
        for index,part in enumerate(parts[1:],1):
            if anchor and index==len(parts)-1:return path.endswith(part) and len(path)-len(part)>=position
            found=path.find(part,position)
            if found<0:return False
            position=found+len(part)
        return True


class SafeWebClient:
    USER_AGENT='OfflineStudioResearch/1.0 (user-directed bounded research)'
    def __init__(self,grant,cancel=None,*,timeout=15,max_bytes=2_000_000,max_requests=18,deadline=None):
        self.grant=grant;self.cancel=cancel or threading.Event();self.timeout=max(.1,min(30,float(timeout)));self.max_bytes=min(8_000_000,max(1024,int(max_bytes)))
        self.max_requests=max_requests;self.requests=0;self.deadline=deadline or time.monotonic()+90;self.robots={}
        self._count_lock=threading.Lock();self._robots_lock=threading.RLock()
    def check(self):
        self.grant.require()
        if self.cancel.is_set():raise InterruptedError('Research cancelled.')
        if time.monotonic()>self.deadline:raise TimeoutError('Research time budget exhausted.')
    def _request(self,url,headers=None,limit=None):
        self.check()
        with self._count_lock:self.requests+=1;over=self.requests>self.max_requests
        if over:raise ResearchError('Research request budget exhausted.')
        p=urlsplit(canonical_url(url));port=p.port or (443 if p.scheme=='https' else 80)
        connection=http.client.HTTPConnection(p.hostname,port,timeout=self.timeout);done=threading.Event();out={};active={};abandoned=threading.Event()
        def execute():
            try:
                addresses=public_addresses(p.hostname,port)
                if abandoned.is_set():return
                self.check()
                # Connect to the validated IP itself. Rebinding cannot change the
                # destination between validation and connection. TLS still checks host/SNI.
                stream=socket.create_connection((addresses[0],port),timeout=self.timeout);active['socket']=stream
                if abandoned.is_set():stream.close();return
                if p.scheme=='https':
                    stream=ssl.create_default_context().wrap_socket(stream,server_hostname=p.hostname);active['socket']=stream
                if abandoned.is_set():stream.close();return
                self.check()
                connection.sock=stream
                request_headers={'User-Agent':self.USER_AGENT,'Accept':'text/html, application/json, text/plain;q=0.8','Accept-Encoding':'identity','Connection':'close'}
                if headers:request_headers.update(headers)
                connection.request('GET',urlunsplit(('','',p.path or '/',p.query,'')),headers=request_headers)
                response=connection.getresponse();maximum=min(limit or self.max_bytes,self.max_bytes)
                declared=response.getheader('Content-Length')
                if declared and (not declared.isdigit() or int(declared)>maximum):raise ResearchError('Download exceeds the configured byte limit.')
                encoding=response.getheader('Content-Encoding','identity').lower()
                if encoding not in {'identity',''}:raise ResearchError('Compressed responses are not accepted by the bounded reader.')
                body=bytearray()
                while True:
                    self.check();block=response.read(min(32768,maximum+1-len(body)))
                    if not block:break
                    body.extend(block)
                    if len(body)>maximum:raise ResearchError('Download exceeds the configured byte limit.')
                out.update(status=response.status,headers={k.lower():v for k,v in response.getheaders()},body=bytes(body),url=url)
            except BaseException as exc:out['error']=exc
            finally:done.set()
        worker=threading.Thread(target=execute,daemon=True,name='bounded-public-web');worker.start();end=min(self.deadline,time.monotonic()+self.timeout)
        try:
            while not done.wait(.025):
                self.check()
                if time.monotonic()>end:raise TimeoutError('The website request timed out.')
            self.check()
            if 'error' in out:raise out['error']
            return out
        finally:
            abandoned.set()
            stream=active.get('socket')
            if stream:
                try:stream.shutdown(socket.SHUT_RDWR)
                except OSError:pass
            connection.close();worker.join(.1)
    def fetch(self,url,*,headers=None,limit=None,robots=True):
        self.check();current=canonical_url(url)
        for _ in range(5):
            self.check()
            if robots:self.check_robots(current)
            result=self._request(current,headers,limit)
            if result['status'] in {301,302,303,307,308}:
                location=result['headers'].get('location')
                if not location:raise ResearchError('Redirect omitted its destination.')
                following=canonical_url(urljoin(current,location))
                if urlsplit(following).netloc!=urlsplit(current).netloc:headers=None
                if urlsplit(current).scheme=='https' and urlsplit(following).scheme!='https':raise ResearchError('HTTPS downgrade redirect rejected.')
                current=following;continue
            if not 200<=result['status']<300:raise ResearchError('Website returned HTTP '+str(result['status']))
            result['url']=current;result['sha256']=hashlib.sha256(result['body']).hexdigest();return result
        raise ResearchError('Website redirect limit exceeded.')
    def check_robots(self,url):
        with self._robots_lock:return self._check_robots(url)
    def _check_robots(self,url):
        p=urlsplit(url);origin=urlunsplit((p.scheme,p.netloc,'/','',''))
        if origin not in self.robots:
            # Robots is checked with the same pinned public network boundary.
            current=urljoin(origin,'robots.txt')
            for _ in range(4):
                response=self._request(current,limit=100_000)
                if response['status'] in {301,302,303,307,308}:
                    location=response['headers'].get('location')
                    if not location:raise ResearchError('Robots redirect omitted its destination.')
                    following=canonical_url(urljoin(current,location))
                    if urlsplit(current).scheme=='https' and urlsplit(following).scheme!='https':raise ResearchError('Robots HTTPS downgrade redirect rejected.')
                    if not urlsplit(following).path.rstrip('/').endswith('robots.txt'):
                        response={'status':404,'headers':{},'body':b''};break
                    current=following;continue
                break
            else:raise ResearchError('Robots redirect limit exceeded.')
            if response['status'] in {404,410}:self.robots[origin]=None
            elif response['status'] in {401,403}:raise ResearchError('Website denies automated reading.')
            elif response['status']!=200:raise ResearchError('Robots policy unavailable; source was not fetched.')
            elif not response['headers'].get('content-type','').lower().startswith('text/plain'):
                # A redirect to a non-robots page is not a policy document.
                self.robots[origin]=None
            else:
                self.robots[origin]=RobotsPolicy(response['body'].decode('utf-8','replace'))
        parser=self.robots[origin]
        if parser and not parser.can_fetch(self.USER_AGENT,url):raise ResearchError('Website robots policy disallows this page.')


class PageExtractor(HTMLParser):
    DROP={'script','style','nav','footer','header','form','svg','noscript','template'}
    def __init__(self,url):
        super().__init__(convert_charrefs=True);self.url=url;self.skip=0;self.title=False;self.title_parts=[];self.parts=[];self.images=[];self.published='';self.canonical=url
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag in self.DROP:self.skip+=1
        if tag=='title':self.title=True
        if tag=='meta':
            key=attrs.get('property',attrs.get('name','')).lower();content=attrs.get('content','')
            if key in {'article:published_time','date','datepublished'}:self.published=content[:100]
            if key in {'og:image','twitter:image'}:self.add_image(content,attrs.get('alt',''))
        if tag=='img':self.add_image(attrs.get('src',''),attrs.get('alt',''))
        if tag=='link' and attrs.get('rel','').lower()=='canonical':
            try:
                candidate=canonical_url(urljoin(self.url,attrs.get('href','')))
                if urlsplit(candidate).hostname==urlsplit(self.url).hostname:self.canonical=candidate
            except (ValueError,ResearchError):pass
        if tag in {'p','div','article','section','h1','h2','h3','li','tr','br'} and not self.skip:self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in self.DROP:self.skip=max(0,self.skip-1)
        if tag=='title':self.title=False
    def handle_data(self,data):
        if self.title:self.title_parts.append(data)
        elif not self.skip:self.parts.append(data)
    def add_image(self,path,alt):
        if not path or len(self.images)>=16:return
        try:url=canonical_url(urljoin(self.url,path))
        except (ValueError,ResearchError):return
        if url not in {r['url'] for r in self.images}:self.images.append({'url':url,'alt':str(alt)[:300],'sourceUrl':self.url,'license':'Not established; inspect the source before reuse.'})


def extract_page(result):
    content_type=result['headers'].get('content-type','').lower()
    if not any(kind in content_type for kind in ['html','text/plain','application/json']):raise ResearchError('This source is not a supported text page.')
    raw=result['body'].decode('utf-8','replace');parser=PageExtractor(result['url'])
    if 'html' in content_type:parser.feed(raw);text=' '.join(parser.parts)
    elif 'json' in content_type:text=json.dumps(json.loads(raw),ensure_ascii=False)
    else:text=raw
    text=re.sub(r'[^\S\n]+',' ',text);text=re.sub(r'\n\s*\n+','\n',text).strip()[:150_000]
    if len(text)<80:raise ResearchError('The page has insufficient readable content; it may require browser rendering.')
    title=' '.join(parser.title_parts).strip()[:240] or urlsplit(result['url']).hostname
    return {'url':result['url'],'canonicalUrl':parser.canonical,'title':title,'domain':urlsplit(result['url']).hostname,'published':parser.published,'retrievedAt':time.time(),'text':text,'contentFingerprint':hashlib.sha256(text.encode()).hexdigest(),'responseFingerprint':result['sha256'],'fetchStatus':'FETCHED','sourceType':'webpage','images':parser.images}


_DDG_PAUSED_UNTIL=[0.0]
_FIXED_ZONES={'Asia/Kolkata':330,'Asia/Calcutta':330,'Asia/Colombo':330,'Asia/Kathmandu':345,'Asia/Dhaka':360,'Asia/Karachi':300,'Asia/Dubai':240,
              'Asia/Muscat':240,'Asia/Riyadh':180,'Asia/Qatar':180,'Asia/Kuwait':180,'Asia/Bahrain':180,'Asia/Baghdad':180,'Asia/Kabul':270,'Asia/Tashkent':300,
              'Asia/Yangon':390,'Asia/Bangkok':420,'Asia/Ho_Chi_Minh':420,'Asia/Jakarta':420,'Asia/Singapore':480,'Asia/Kuala_Lumpur':480,'Asia/Shanghai':480,
              'Asia/Hong_Kong':480,'Asia/Taipei':480,'Asia/Manila':480,'Asia/Tokyo':540,'Asia/Seoul':540,'Africa/Nairobi':180,'Africa/Lagos':60,
              'Africa/Johannesburg':120,'Africa/Cairo':120,'Europe/Moscow':180,'Europe/Istanbul':180,'America/Sao_Paulo':-180,'UTC':0}


# Questions whose answer changes over time also get a news search in the 'web' composite.
FRESH=re.compile(r'\b(?:latest|news|today|tonight|right now|nowadays|these days|as of now|yesterday|tomorrow|this (?:week|month|year)|current(?:ly)?|recent(?:ly)?|update[sd]?|price[sd]?|cost|rate|score|won|wins?|winner|results?|election|launch(?:ed|es)?|released?|announced?|stock|weather|match|20(?:2[4-9]|[3-9]\d))\b',re.I)


class SearchProviders:
    """Documented search APIs through the same bounded public network client.

    ``public`` combines no-key encyclopedia/scholarly discovery within one query
    budget. It is explicitly not internet-wide search. Image discovery uses
    Commons metadata; a search result does not imply the image was downloaded.
    """
    CAPABILITIES={
        'none':{'breadth':'direct URLs only','web':False,'images':False,'keyRequired':False},
        'web':{'breadth':'Internet-wide results (DuckDuckGo Lite) + Bing News for current events + Wikipedia; no key; pages read under robots rules','web':True,'images':True,'keyRequired':False},
        'public':{'breadth':'Wikipedia encyclopedia + Crossref scholarly metadata; not internet-wide','web':True,'images':True,'keyRequired':False},
        'wikimedia':{'breadth':'Wikipedia encyclopedia; not internet-wide','web':True,'images':True,'keyRequired':False},
        'wikipedia':{'breadth':'Wikipedia encyclopedia; not internet-wide','web':True,'images':True,'keyRequired':False},
        'commons':{'breadth':'Wikimedia Commons media metadata; not general web search','web':False,'images':True,'keyRequired':False},
        'crossref':{'breadth':'Crossref scholarly metadata; not full publisher text or internet-wide','web':True,'images':False,'keyRequired':False},
        'searxng':{'breadth':'Configured SearXNG instance and its enabled engines','web':True,'images':True,'keyRequired':False},
        'brave':{'breadth':'Brave internet-wide search API; user-controlled subscription/quota','web':True,'images':True,'keyRequired':True},
    }
    def __init__(self,client,settings,secret=''):
        self.client=client;self.settings=settings;self.secret=secret;self.query_count=0;self.reference_query_count=0;self.last_meta={};self.responses=[]
        self.query_budget=max(1,min(4,int(settings.get('research_max_queries',2))));self.reference_budget=1
        # One query to each of the composite's engines (web results, news, encyclopedia).
        if settings.get('research_provider')=='web':self.query_budget=max(self.query_budget,3)
    @classmethod
    def capabilities(cls,provider):
        return dict(cls.CAPABILITIES.get(provider,cls.CAPABILITIES['none']))
    @staticmethod
    def plain(value,limit=1000):
        parser=PageExtractor('https://en.wikipedia.org/');parser.feed(str(value or '')[:max(1000,limit*3)])
        return re.sub(r'\s+',' ',''.join(parser.parts)).strip()[:limit]
    @staticmethod
    def checked_url(value):
        url=canonical_url(value)
        try:address=ipaddress.ip_address(urlsplit(url).hostname)
        except ValueError:return url
        if not address.is_global or address.is_multicast:raise ResearchError('Private/reserved result URL rejected.')
        return url
    def _json(self,url,headers=None,limit=750_000):
        # Explicit API endpoints are requested as APIs, not crawled HTML. They
        # retain the identical destination/TLS/redirect/byte/time boundary.
        response=self.client.fetch(url,headers=headers,robots=False,limit=limit)
        if 'json' not in response.get('headers',{}).get('content-type','').lower():raise ResearchError('Provider did not return JSON. For SearXNG, enable JSON output on the selected instance.')
        try:data=json.loads(response['body'])
        except (ValueError,TypeError):raise ResearchError('Provider returned malformed JSON.') from None
        if not isinstance(data,dict):raise ResearchError('Provider JSON schema was not an object.')
        if data.get('error'):raise ResearchError('Provider reported an API error; check configuration, query, quota and credentials.')
        self.responses.append({'url':response['url'],'responseFingerprint':response['sha256'],'bytes':len(response['body']),'retrievedAt':time.time()})
        return data,response
    def _query(self,url,headers=None,reference=False):
        if reference:
            if self.reference_query_count>=self.reference_budget:raise ResearchError('Configured visual reference query budget exhausted.')
            self.client.check();self.reference_query_count+=1
        else:
            if self.query_count>=self.query_budget:raise ResearchError('Configured discovery query budget exhausted.')
            self.client.check();self.query_count+=1
        return self._json(url,headers)
    def search(self,query,images=False,page=1,limit=8,engines=None):
        self.client.check();provider=self.settings.get('research_provider','none');query=str(query).strip()[:400]
        if not query:raise ResearchError('Enter a nonempty discovery query.')
        page=max(1,min(5,int(page)));limit=max(1,min(20,int(limit)));started=time.monotonic();before=self.query_count;before_ref=self.reference_query_count;before_responses=len(self.responses)
        if provider not in self.CAPABILITIES or provider=='none':raise ResearchError('No search provider configured. Choose Public discovery (encyclopedia/scholarly), configure SearXNG/Brave, or include public URLs.')
        rows=[];errors=[];groups=[]
        if provider in {'public','web'} and not images:
            sources=['wikimedia','crossref'] if provider=='public' else list(engines or ['ddg']+(['bingnews'] if FRESH.search(query) else [])+['wikimedia'])
            for source in sources:
                if self.query_count>=self.query_budget:break
                try:groups.append(self._search(source,query,False,page,limit))
                except (InterruptedError,PermissionError):raise
                except Exception as exc:errors.append(source+': '+str(exc)[:240])
            # Web results blocked (human check): current news still answers most open questions.
            if provider=='web' and 'bingnews' not in sources and any(e.startswith('ddg:') for e in errors):
                try:groups.insert(0,self._search('bingnews',query,False,page,limit))
                except (InterruptedError,PermissionError):raise
                except Exception as exc:errors.append('bingnews: '+str(exc)[:240])
            rows=[group[index] for index in range(limit) for group in groups if index<len(group)]
            if not rows and errors:raise ResearchError('; '.join(errors))
        else:rows=self._search(provider,query,images,page,limit)
        unique={}
        for row in rows:
            key=row.get('imageUrl') if images else row['url']
            if key and key not in unique:unique[key]=row
        # Public composite keeps some results from each successful domain.
        result=list(unique.values())[:limit*2 if provider in {'public','web'} and not images else limit]
        self.last_meta={'provider':provider,'breadth':self.capabilities(provider)['breadth'],'images':bool(images),'page':page,'resultsCount':len(result),'queriesSent':(self.query_count-before)+(self.reference_query_count-before_ref),'totalQueriesSent':self.query_count,'totalReferenceQueriesSent':self.reference_query_count,'latencyMs':round((time.monotonic()-started)*1000,2),'errors':errors,'nextPage':page+1 if result and page<5 else None,'responseEvidence':self.responses[before_responses:]}
        return result
    def _search(self,provider,query,images,page,limit):
        if images and provider in {'public','web','wikimedia','wikipedia','commons'}:return self._commons(query,page,limit,reference=True)
        if provider=='ddg':return self._duckduckgo(query,limit)
        if provider=='bingnews':return self._bing_news(query,limit)
        if provider=='weather':return self._weather(query,limit)
        offset=(page-1)*limit
        if provider=='searxng':
            endpoint=canonical_url(self.settings.get('research_endpoint',''));data,_=self._query(endpoint+('&' if '?' in endpoint else '?')+urlencode({'q':query,'format':'json','categories':'images' if images else 'general','pageno':page}))
            if not isinstance(data.get('results'),list):raise ResearchError('SearXNG JSON has no results array; JSON search may be disabled.')
            return self._normalize(data['results'],provider,images,limit)
        if provider=='brave':
            if not self.secret:raise ResearchError('Brave Search is selected, but its API key is not configured.')
            endpoint='https://api.search.brave.com/res/v1/'+('images' if images else 'web')+'/search?'+urlencode({'q':query,'count':limit,'offset':page-1})
            data,_=self._query(endpoint,{'X-Subscription-Token':self.secret,'Accept':'application/json'})
            web=data.get('web') or {}
            if not isinstance(web,dict):raise ResearchError('Brave response has an unexpected web schema.')
            rows=data.get('results',[]) if images else web.get('results',[])
            if not isinstance(rows,list):raise ResearchError('Brave response has an unexpected result schema.')
            return self._normalize(rows,provider,images,limit)
        if provider in {'wikimedia','wikipedia'}:
            params={'action':'query','list':'search','srsearch':query,'srlimit':limit,'sroffset':offset,'format':'json','formatversion':2,'maxlag':5}
            data,_=self._query('https://en.wikipedia.org/w/api.php?'+urlencode(params));rows=data.get('query',{}).get('search',[])
            if not isinstance(rows,list):raise ResearchError('Wikipedia response has no search array.')
            result=[]
            for row in rows[:limit]:
                try:
                    ident=int(row['pageid']);title=self.plain(row['title'],240)
                    if ident<=0:continue
                    result.append(dict(self.result('https://en.wikipedia.org/wiki/'+quote(title.replace(' ','_'),safe=''),title,self.plain(row.get('snippet',''))),provider='wikimedia',metadataId=str(ident),published=str(row.get('timestamp',''))[:100],scope='encyclopedia article discovery'))
                except (KeyError,ValueError,TypeError,ResearchError):continue
            return result
        if provider=='crossref':
            if images:raise ResearchError('Crossref offers scholarly metadata, not image discovery.')
            data,_=self._query('https://api.crossref.org/works?'+urlencode({'query':query,'rows':limit,'offset':offset}));rows=data.get('message',{}).get('items',[])
            if not isinstance(rows,list):raise ResearchError('Crossref response has no work items array.')
            result=[]
            for row in rows[:limit]:
                doi=str(row.get('DOI',''))
                if not doi or len(doi)>300:continue
                title=(row.get('title') or ['Untitled scholarly work'])[0]
                try:result.append(dict(self.result('https://doi.org/'+quote(doi,safe='/'),self.plain(title,240),self.plain(row.get('abstract',''))),provider='crossref',metadataId=doi,published=self._crossref_date(row),scope='scholarly metadata; publisher full text not read'))
                except (ValueError,ResearchError):continue
            return result
        if provider=='commons':return self._commons(query,page,limit)
        raise ResearchError('Unsupported discovery provider.')
    def _page(self,url):
        # Keyless HTML/RSS endpoints are read like pages: robots rules apply and the query budget counts them.
        if self.query_count>=self.query_budget:raise ResearchError('Configured discovery query budget exhausted.')
        self.client.check();self.query_count+=1
        response=self.client.fetch(url,limit=600_000)
        self.responses.append({'url':response['url'],'responseFingerprint':response['sha256'],'bytes':len(response['body']),'retrievedAt':time.time()})
        return response['body'].decode('utf-8','replace'),response
    def _duckduckgo(self,query,limit):
        # After a human check, stay away for 15 minutes instead of repeating automated queries.
        if time.time()<_DDG_PAUSED_UNTIL[0]:raise ResearchError('DuckDuckGo paused after a human check; other sources used.')
        body,response=self._page('https://lite.duckduckgo.com/lite/?'+urlencode({'q':query,'kl':'wt-wt'}))
        # A human check is reported, never worked around.
        if response.get('status')!=200 or re.search(r'anomaly|captcha',body[:20000],re.I) and 'result-link' not in body:
            _DDG_PAUSED_UNTIL[0]=time.time()+900;raise ResearchError('DuckDuckGo asked for a human check; web results skipped.')
        result=[];snippets=re.findall(r"class=['\"]result-snippet['\"][^>]*>(.*?)</td>",body,re.S)
        links=re.findall(r"<a[^>]*href=['\"]([^'\"]+)['\"][^>]*class=['\"]result-link['\"][^>]*>(.*?)</a>",body,re.S)
        for index,(href,title) in enumerate(links):
            href=html.unescape(href);target=parse_qs(urlsplit(href).query).get('uddg',[''])[0] if '/l/?' in href else href
            if not target.startswith(('http://','https://')):continue
            host=(urlsplit(target).hostname or '').lower()
            if host.endswith('duckduckgo.com') or 'ad_domain=' in target:continue
            try:result.append(dict(self.result(target,self.plain(title,240),self.plain(snippets[index] if index<len(snippets) else '')),provider='duckduckgo',scope='web search result; page read separately'))
            except (ValueError,ResearchError):continue
            if len(result)>=limit:break
        return result
    def _weather(self,place,limit):
        """Live forecast as a citable source: Open-Meteo geocoding, then MET Norway's forecast API.

        Measured 2026-11-08: news pages carry no live weather, so "weather in Pune today" got a refusal.
        Both endpoints allow automated access under robots rules; Open-Meteo's forecast endpoint does not.
        """
        body,_=self._page('https://geocoding-api.open-meteo.com/v1/search?'+urlencode({'name':place,'count':1,'language':'en','format':'json'}))
        try:hit=(json.loads(body).get('results') or [])[0]
        except (ValueError,IndexError,AttributeError):raise ResearchError('No place found for the weather question.') from None
        lat=round(float(hit['latitude']),3);lon=round(float(hit['longitude']),3)
        name=', '.join(str(part) for part in [hit.get('name'),hit.get('admin1'),hit.get('country')] if part)
        url=f'https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={lat}&lon={lon}'
        url=self.checked_url(url)
        return [dict(url=url,title='Weather forecast for '+name+' (MET Norway)',snippet='Live forecast data for '+name+'.',provider='weather',
                     metadataId=json.dumps({'lat':lat,'lon':lon,'name':name,'timezone':hit.get('timezone','')}),scope='live weather forecast API')]
    def _weather_page(self,row):
        meta=json.loads(row.get('metadataId') or '{}')
        body,response=self._page(row['url'])
        try:series=json.loads(body)['properties']['timeseries']
        except (ValueError,KeyError,TypeError):raise ResearchError('Weather service returned no forecast.') from None
        if not series:raise ResearchError('Weather service returned no forecast.')
        from datetime import datetime,timedelta,timezone as _tz
        try:
            from zoneinfo import ZoneInfo;zone=ZoneInfo(meta.get('timezone') or 'UTC')
        except Exception:
            # This Python has no tz database; zones without daylight saving are exact from a fixed offset.
            minutes=_FIXED_ZONES.get(meta.get('timezone',''))
            zone=_tz(timedelta(minutes=minutes),'local') if minutes is not None else None
        def local(stamp):
            moment=datetime.fromisoformat(stamp.replace('Z','+00:00'))
            return moment.astimezone(zone).strftime('%a %d %b %H:%M') if zone else moment.strftime('%a %d %b %H:%M UTC')
        def describe(entry):
            data=entry.get('data',{});now=data.get('instant',{}).get('details',{})
            nxt=data.get('next_1_hours') or data.get('next_6_hours') or {}
            sky=re.sub(r'_(?:day|night|polartwilight)$','',str(nxt.get('summary',{}).get('symbol_code','')))
            sky=re.sub(r'(clear|partly|light|heavy|rain|sleet|snow)(?=[a-z])',r'\1 ',sky).replace('and thunder',' and thunder').strip()
            rain=nxt.get('details',{}).get('precipitation_amount')
            return (f"{now.get('air_temperature')} °C, {sky or 'conditions n/a'}, humidity {now.get('relative_humidity')}%, wind {now.get('wind_speed')} m/s"
                    +(f", rain {rain} mm" if rain is not None else ''))
        first=series[0];lines=[f"Weather for {meta.get('name','the place')} - forecast updated {local(first['time'])}.",'Now: '+describe(first)]
        day=[entry for entry in series[:25] if entry.get('data',{}).get('instant',{}).get('details',{}).get('air_temperature') is not None]
        temps=[entry['data']['instant']['details']['air_temperature'] for entry in day]
        if temps:lines.append(f'Next 24 hours: low {min(temps)} °C, high {max(temps)} °C.')
        for entry in series[3:25:3]:lines.append(local(entry['time'])+': '+describe(entry))
        lines.append('Data: MET Norway (CC BY 4.0); place lookup: Open-Meteo.')
        return self._api_evidence(row['url'],row['title'],'\n'.join(lines),response,'live_weather_forecast',published=first['time'],
                                  coverage='Point forecast from the MET Norway Locationforecast API.',license='MET Norway data, CC BY 4.0 (attribution: MET Norway).')
    def _bing_news(self,query,limit):
        params={'q':query,'format':'rss'}
        # "Latest" questions want the newest articles, not the most relevant old ones (ISRO returned 2023 news).
        if re.search(r'\b(?:latest|news|today|recent(?:ly)?|this (?:week|month)|yesterday|now|current(?:ly)?)\b',query,re.I):params['qft']='sortbydate="1"'
        body,_=self._page('https://www.bing.com/news/search?'+urlencode(params))
        result=[]
        for item in re.findall(r'<item>(.*?)</item>',body,re.S)[:limit*2]:
            field=lambda name:html.unescape(re.sub(r'<!\[CDATA\[|\]\]>','',(re.search('<'+name+r'>(.*?)</'+name+'>',item,re.S) or [None,''])[1])).strip()
            link=field('link');target=parse_qs(urlsplit(link).query).get('url',[link])[0]
            if not target.startswith(('http://','https://')):continue
            try:result.append(dict(self.result(target,self.plain(field('title'),240),self.plain(field('description'))),provider='bingnews',published=field('pubDate')[:100],scope='news result; article read separately'))
            except (ValueError,ResearchError):continue
            if len(result)>=limit:break
        return result
    def _normalize(self,rows,provider,images,limit):
        result=[]
        for row in rows[:limit*3]:
            if not isinstance(row,dict):continue
            properties=row.get('properties') or {}
            if not isinstance(properties,dict):continue
            image=(row.get('img_src') or properties.get('url','')) if images else ''
            try:result.append(dict(self.result(row.get('url',''),self.plain(row.get('title',''),240),self.plain(row.get('content') or row.get('description','')),image),provider=provider,downloadUrl=self.checked_url(image) if image else '',scope='discovered result; target page not read'))
            except (ValueError,ResearchError):continue
        return result
    def _commons(self,query,page,limit,reference=False):
        # Literal phrase reduces unrelated lookalike vehicle matches. The UI
        # still requires a human to inspect the actual variant/reference.
        params={'action':'query','generator':'search','gsrsearch':'"'+query.replace('"','')+'"','gsrnamespace':6,'gsrlimit':limit,'gsroffset':(page-1)*limit,'prop':'imageinfo','iiprop':'url|size|mime|extmetadata','iiurlwidth':1000,'format':'json','formatversion':2,'maxlag':5}
        data,_=self._query('https://commons.wikimedia.org/w/api.php?'+urlencode(params),reference=reference);pages=data.get('query',{}).get('pages',[])
        if isinstance(pages,dict):pages=list(pages.values())
        if not isinstance(pages,list):raise ResearchError('Commons response has no page metadata array.')
        result=[]
        for row in sorted(pages,key=lambda r:r.get('index',999)):
            info=(row.get('imageinfo') or [{}])[0];mime=info.get('mime','')
            if mime not in {'image/jpeg','image/png','image/webp'}:continue
            metadata=info.get('extmetadata',{});value=lambda key:self.plain(metadata.get(key,{}).get('value',''),1000)
            try:
                source=self.checked_url(info['descriptionurl']);image=self.checked_url(info.get('thumburl') or info['url']);original=self.checked_url(info['url']);license_url=value('LicenseUrl')
                result.append(dict(self.result(source,self.plain(row.get('title',''),240),value('ImageDescription'),image),provider='commons',metadataId=str(int(row['pageid'])),sourceUrl=source,downloadUrl=image,originalImageUrl=original,alt=value('ImageDescription'),mime=mime,width=int(info.get('thumbwidth') or info.get('width') or 0),height=int(info.get('thumbheight') or info.get('height') or 0),originalWidth=int(info.get('width') or 0),originalHeight=int(info.get('height') or 0),license=value('LicenseShortName') or 'Not established',licenseUrl=self.checked_url(license_url) if license_url else '',artist=value('Artist'),credit=value('Credit'),attributionRequired=value('AttributionRequired').lower()=='true',restrictions=value('Restrictions'),published=value('DateTimeOriginal'),scope='Commons file metadata; image bytes not downloaded',status='DISCOVERED_NOT_DOWNLOADED'))
            except (KeyError,ValueError,TypeError,ResearchError):continue
        return result[:limit]
    @staticmethod
    def _crossref_date(row):
        parts=(row.get('published',{}).get('date-parts') or row.get('published-online',{}).get('date-parts') or [[]])[0]
        return '-'.join(str(value).zfill(4 if index==0 else 2) for index,value in enumerate(parts[:3]))
    def probe(self,query='Royal Enfield Hunter 350',images=False):
        started=time.monotonic()
        try:
            rows=self.search(query,images=images,limit=3)
            return dict(self.last_meta,status='AVAILABLE' if rows else 'RESPONDED_EMPTY',jsonCapable=True,connectionVerified=True,results=rows,verification='Actual API response parsed; page/image content acceptance is separate.')
        except (InterruptedError,PermissionError):raise
        except Exception as exc:return {'status':'UNAVAILABLE','provider':self.settings.get('research_provider','none'),'breadth':self.capabilities(self.settings.get('research_provider','none'))['breadth'],'connectionVerified':False,'jsonCapable':False,'error':str(exc)[:500],'latencyMs':round((time.monotonic()-started)*1000,2),'queriesSent':self.query_count}
    def fetch_result(self,row):
        """Read an actually discovered result using its documented public API.

        Wikipedia returns article text; Crossref returns metadata/abstract only.
        All other targets use the ordinary robots-enforcing page reader.
        """
        self.client.check();provider=row.get('provider')
        if provider=='weather':return self._weather_page(row)
        if provider=='wikimedia':
            ident=int(row.get('metadataId','0'))
            if ident<=0:raise ResearchError('Invalid discovered Wikipedia page identity.')
            params={'action':'query','prop':'extracts|info|revisions|extlinks','pageids':ident,'explaintext':1,'exchars':1200,'inprop':'url','rvprop':'timestamp|ids','ellimit':30,'format':'json','formatversion':2,'maxlag':5}
            data,response=self._json('https://en.wikipedia.org/w/api.php?'+urlencode(params));pages=data.get('query',{}).get('pages',[])
            if not pages or pages[0].get('missing'):raise ResearchError('Discovered Wikipedia article no longer exists.')
            page=pages[0];text=str(page.get('extract','')).strip();url=self.checked_url(page.get('canonicalurl') or page.get('fullurl') or row['url'])
            if int(page.get('pageid',0))!=ident:raise ResearchError('Wikipedia page identity changed.')
            if urlsplit(url).hostname!='en.wikipedia.org':raise ResearchError('Wikipedia canonical host changed.')
            if len(text)<80:raise ResearchError('Discovered article has insufficient readable extract.')
            revisions=page.get('revisions') or [{}]
            external=[]
            for link in page.get('extlinks',[])[:30]:
                try:external.append(self.checked_url(link.get('url') or link.get('*','')))
                except (ValueError,ResearchError):continue
            return self._api_evidence(url,page.get('title') or row.get('title',''),text,response,'encyclopedia_excerpt',published=revisions[0].get('timestamp',''),revisionId=revisions[0].get('revid'),externalLinks=list(dict.fromkeys(external)),coverage='Official TextExtracts excerpt, up to 1,200 characters; not a full-article archive.',license='Wikipedia content license applies; inspect the article history/attribution before reuse.')
        if provider=='crossref':
            doi=str(row.get('metadataId',''))
            if not doi or len(doi)>300:raise ResearchError('Invalid discovered DOI identity.')
            data,response=self._json('https://api.crossref.org/works/'+quote(doi,safe=''));work=data.get('message',{})
            if not isinstance(work,dict) or str(work.get('DOI','')).casefold()!=doi.casefold():raise ResearchError('Crossref work identity changed.')
            title=self.plain((work.get('title') or ['Untitled scholarly work'])[0],240);abstract=self.plain(work.get('abstract',''),12000);text=title+'\n'+abstract+'\nPublisher: '+self.plain(work.get('publisher',''),300)+'\nPublished: '+self._crossref_date(work)+'\nDOI: '+doi
            return self._api_evidence(self.checked_url('https://doi.org/'+quote(doi,safe='/')),title,text,response,'scholarly_metadata',published=self._crossref_date(work),coverage='Crossref deposited metadata and abstract, where present; publisher full text was not read.',license='Metadata does not imply publisher full-text/image reuse rights.')
        return extract_page(self.client.fetch(row['url']))
    @staticmethod
    def _api_evidence(url,title,text,response,source_type,**metadata):
        return dict(url=url,canonicalUrl=url,title=str(title)[:240],domain=urlsplit(url).hostname,retrievedAt=time.time(),text=text[:150000],contentFingerprint=hashlib.sha256(text.encode()).hexdigest(),responseFingerprint=response['sha256'],fetchStatus='FETCHED',sourceType=source_type,images=[],apiUrl=response['url'],**metadata)
    @staticmethod
    def result(url,title,snippet,image=''):
        return {'url':SearchProviders.checked_url(url),'title':str(title)[:240],'snippet':str(snippet)[:1000],'imageUrl':SearchProviders.checked_url(image) if image else '', 'status':'DISCOVERED_NOT_READ'}
