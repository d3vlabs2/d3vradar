"""Read a public job page into a reviewable import draft; never saves or applies."""
import http.client
import ipaddress
import json
import re
import socket
import ssl
import time
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlsplit,urljoin,urlunsplit

MAX_PAGE=2_000_000
BLOCKED_SUFFIXES=('.localhost','.local','.internal','.home','.lan')


def public_target(url):
    if len(url)>2000 or any(ord(c)<32 for c in url):raise ValueError('Enter a valid public HTTPS job URL.')
    try:
        p=urlsplit(url)
        if p.scheme!='https' or not p.hostname or p.username is not None or p.password is not None or p.port not in (None,443):raise ValueError()
        host=p.hostname.encode('idna').decode('ascii').lower().rstrip('.')
        if '.' not in host or host=='localhost' or host.endswith(BLOCKED_SUFFIXES):raise ValueError()
        addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
        ips=list(dict.fromkeys(a[4][0] for a in addresses))
        if not ips or any(not ipaddress.ip_address(ip).is_global or ipaddress.ip_address(ip).is_multicast or ipaddress.ip_address(ip).is_reserved for ip in ips):raise ValueError()
    except (ValueError,UnicodeError,OSError):raise ValueError('Only public HTTPS job pages are supported; local or private addresses cannot be fetched.') from None
    return p,host,ips[0]


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self,host,ip,timeout):
        super().__init__(host,timeout=timeout,context=ssl.create_default_context())
        self.pinned_ip=ip
    def connect(self):
        # Connect to the checked IP; TLS still validates the original hostname.
        sock=socket.create_connection((self.pinned_ip,443),timeout=self.timeout)
        try:self.sock=self._context.wrap_socket(sock,server_hostname=self.host)
        except Exception:sock.close();raise


def fetch_page(url):
    started=time.monotonic()
    for _ in range(4):
        p,host,ip=public_target(url)
        connection=PinnedHTTPS(host,ip,timeout=8)
        try:
            target=urlunsplit(('','',p.path or '/',p.query,''))
            connection.request('GET',target,headers={'Accept':'text/html,application/xhtml+xml','Accept-Encoding':'identity','User-Agent':'D3VJobRadar/2.4 (user-requested public job import)'})
            response=connection.getresponse()
            if response.status in (301,302,303,307,308):
                location=response.getheader('Location')
                if not location:raise ValueError('The page redirected without a destination. Paste its description instead.')
                url=urljoin(url,location)
                continue
            if response.status!=200:raise ValueError(f'The site returned HTTP {response.status}. Open it in your browser and paste the description instead.')
            content_type=response.getheader('Content-Type','')
            if content_type.split(';')[0].strip().lower() not in ('text/html','application/xhtml+xml'):
                raise ValueError('This URL is not a readable HTML job page. Paste the description instead.')
            if response.getheader('Content-Encoding','identity').lower() not in ('','identity'):
                raise ValueError('The site returned an unsupported page format. Paste the description instead.')
            chunks=[];size=0
            while True:
                if time.monotonic()-started>25:raise ValueError('Fetching timed out. Paste the description instead.')
                data=response.read(min(65536,MAX_PAGE+1-size))
                if not data:break
                size+=len(data)
                if size>MAX_PAGE:raise ValueError('This page is too large to import. Paste the description instead.')
                chunks.append(data)
            charset=re.search(r'charset=([\w-]+)',content_type,re.I)
            try:text=b''.join(chunks).decode(charset.group(1) if charset else 'utf-8',errors='replace')
            except LookupError:text=b''.join(chunks).decode('utf-8',errors='replace')
            return text,url
        except (OSError,http.client.HTTPException):
            raise ValueError('The public job page could not be reached. Open it in your browser and paste the description instead.') from None
        finally:connection.close()
    raise ValueError('Too many redirects. Paste the description from the final job page instead.')


class PageText(HTMLParser):
    VOID={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
    SKIP={'script','style','noscript','nav','header','footer','aside','form','button','svg','template'}
    BLOCK={'p','br','li','div','section','h1','h2','h3','h4','ul','ol'}
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack=[];self.structured=[];self.script=None
        self.body=[];self.focus=[];self.titles=[];self.meta={};self.headings=[]
    def skipped(self):return any(tag in self.SKIP for tag,main in self.stack)
    def focused(self):return any(main for tag,main in self.stack)
    def newline(self):
        if not self.skipped():
            self.body.append('\n')
            if self.focused():self.focus.append('\n')
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='meta':
            key=attrs.get('property') or attrs.get('name') or attrs.get('itemprop')
            if key:self.meta[key.lower()]=attrs.get('content','')
        if tag=='script' and attrs.get('type','').lower().split(';')[0]=='application/ld+json':self.script=[]
        if tag in self.BLOCK:self.newline()
        if tag not in self.VOID:self.stack.append((tag,tag in ('main','article') or attrs.get('role')=='main'))
    def handle_endtag(self,tag):
        if tag=='script' and self.script is not None:
            self.structured.append(''.join(self.script));self.script=None
        if tag in self.BLOCK:self.newline()
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i][0]==tag:
                del self.stack[i:];break
    def handle_data(self,data):
        if self.script is not None:self.script.append(data);return
        if self.skipped():return
        if any(tag=='title' for tag,main in self.stack):self.titles.append(data);return
        if any(tag=='h1' for tag,main in self.stack):self.headings.append(data)
        self.body.append(data)
        if self.focused():self.focus.append(data)


def plain(value):
    parser=PageText();parser.feed(unescape(str(value or '')))
    lines=[re.sub(r'\s+',' ',line).strip() for line in unescape(''.join(parser.body)).splitlines()]
    return '\n'.join(line for line in lines if line).strip()[:60000]


def postings(value,depth=0):
    if depth>15:return
    if isinstance(value,dict):
        kind=value.get('@type',[])
        if kind=='JobPosting' or isinstance(kind,list) and 'JobPosting'in kind:yield value
        for child in value.values():yield from postings(child,depth+1)
    elif isinstance(value,list):
        for child in value[:500]:yield from postings(child,depth+1)


def extract_page(html,url):
    parser=PageText();parser.feed(html)
    found=[]
    for block in parser.structured:
        try:found.extend(postings(json.loads(block)))
        except (ValueError,RecursionError):continue
    if len(found)>1:raise ValueError('This page contains several jobs. Open the individual job and use its URL.')
    details={'url':url,'title':'','company':'','location':'','workplace':'unknown','salary':''}
    if found:
        row=found[0];description=plain(row.get('description'))
        details['title']=plain(row.get('title'))[:300]
        org=row.get('hiringOrganization') or {};details['company']=plain(org.get('name') if isinstance(org,dict) else org)[:250]
        locations=row.get('jobLocation') or []
        if isinstance(locations,dict):locations=[locations]
        labels=[]
        for location in locations if isinstance(locations,list) else []:
            if not isinstance(location,dict):continue
            address=location.get('address') or {}
            if isinstance(address,dict):labels.append(', '.join(str(address[k]) for k in ('addressLocality','addressRegion','addressCountry') if isinstance(address.get(k),str)))
        details['location']='; '.join(x for x in labels if x)[:250]
        if row.get('jobLocationType')=='TELECOMMUTE':details['workplace']='remote'
        salary=row.get('baseSalary') or {}
        if isinstance(salary,dict):
            value=salary.get('value') or {}
            if isinstance(value,dict):details['salary']=' '.join(str(x) for x in [salary.get('currency'),value.get('value') or value.get('minValue'),('– '+str(value['maxValue'])) if value.get('maxValue') else '',value.get('unitText')] if x is not None and x!='')[:200]
        method='JobPosting structured data'
    else:
        text=''.join(parser.focus) or ''.join(parser.body)
        description='\n'.join(re.sub(r'\s+',' ',line).strip() for line in text.splitlines() if line.strip())[:60000]
        if not parser.focus or not re.search(r'\b(responsibilit\w*|qualifications?|requirements?|job description|about (the|this) (role|job)|what you.ll do)\b',description,re.I):
            raise ValueError('No reliable job description was found. The page may require login or JavaScript; paste the description instead.')
        details['title']=plain(''.join(parser.headings) or parser.meta.get('og:title') or ''.join(parser.titles))[:300]
        method='Public main/article text (review required)'
    # Explicit page metadata fills gaps; never infer employer from a job-board name.
    for field,keys in {
        'company':('hiringorganization','company','companyname','job:company'),
        'location':('job:location','joblocation','location'),
        'salary':('job:salary','salary'),
    }.items():
        if not details[field]:
            details[field]=next((plain(parser.meta[k])[:250] for k in keys if parser.meta.get(k)), '')
    if details['workplace']=='unknown':
        context=details['title']+' '+details['location']+' '+description
        if re.search(r'\bhybrid\b',context,re.I):details['workplace']='hybrid'
        elif re.search(r'\b(?:fully remote|100% remote|remote position|remote role|work from home)\b',context,re.I):details['workplace']='remote'
        elif re.search(r'\b(?:on-site|onsite|on site)\b',details['title']+' '+details['location'],re.I):details['workplace']='onsite'
    if len(description)<80:raise ValueError('The site did not provide enough readable job text. Paste the full description instead.')
    details.update(description=description,method=method,reviewRequired=True)
    return details


def fetch_details(url):
    html,final_url=fetch_page(url)
    return extract_page(html,final_url)
