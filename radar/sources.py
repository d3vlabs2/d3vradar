import asyncio, json, os, re, time, hashlib, html
from urllib.parse import urlparse, quote_plus
import httpx
from .apply import source_audit
from .catalog import expand_boards
from .store import db,upsert_jobs,get_setting,DEFAULT_SEARCH,current_workspace,cached_public_feed,cache_public_feed

BOARDS=[
 {'id':'remotive','name':'Remotive','url':'https://remotive.com','mode':'api'},
 {'id':'himalayas','name':'Himalayas','url':'https://himalayas.app','mode':'api'},
 {'id':'canonical','name':'Canonical','url':'https://canonical.com/careers','mode':'greenhouse'},
 {'id':'cloudflare','name':'Cloudflare','url':'https://cloudflare.com/careers','mode':'greenhouse'},
 {'id':'gitlab','name':'GitLab','url':'https://about.gitlab.com/jobs','mode':'greenhouse'},
 {'id':'dice','name':'Dice','url':'https://www.dice.com','mode':'mcp','endpoint':'https://mcp.dice.com/mcp','domain':'dice.com'},
 {'id':'ziprecruiter','name':'ZipRecruiter','url':'https://www.ziprecruiter.com','mode':'mcp','endpoint':'https://api.ziprecruiter.com/mcp','domain':'ziprecruiter.com'},
 {'id':'obra','name':'Obra','url':'https://app.obrajobs.com','mode':'indexed','domain':'obrajobs.com'},
 {'id':'linkedin','name':'LinkedIn','url':'https://www.linkedin.com/jobs','mode':'indexed','domain':'linkedin.com/jobs/view'},
 {'id':'bandana','name':'Bandana','url':'https://bandana.com','mode':'indexed','domain':'bandana.com'},
 {'id':'glassdoor','name':'Glassdoor','url':'https://www.glassdoor.com/Job','mode':'indexed','domain':'glassdoor.com/job-listing'},
 {'id':'indeed','name':'Indeed','url':'https://www.indeed.com','mode':'indexed','domain':'indeed.com/viewjob'},
 {'id':'teal','name':'Teal Jobs','url':'https://www.tealhq.com/jobs','mode':'indexed','domain':'tealhq.com/job','about':'Teal job discovery. Search links and import work without an API key; indexed discovery needs your Brave key.'},
 {'id':'greenhouse','name':'Greenhouse discovery','url':'https://www.greenhouse.com/for-job-seekers','mode':'indexed','domain':'job-boards.greenhouse.io','domains':['job-boards.greenhouse.io','boards.greenhouse.io'],'about':'Search public employer job boards. This does not access a private MyGreenhouse account or its recommendations.'},
 {'id':'ashby','name':'Ashby careers','url':'https://www.ashbyhq.com/careers','mode':'ashby','board':'Ashby','about':'Ashby’s own company openings, not every employer using Ashby.'},
 {'id':'jobleads','name':'JobLeads','url':'https://www.jobleads.com/home','mode':'indexed','domain':'jobleads.com','about':'Search links, job import, and optional indexed discovery. Some listings require a JobLeads account.'},
 {'id':'jobilize','name':'Jobilize','url':'https://www.jobilize.com/','mode':'indexed','domain':'jobilize.com','about':'Search links, job import, and optional indexed discovery.'},
]

BOARDS=expand_boards(BOARDS)

def clean(x):return re.sub(r'\s+',' ',html.unescape(re.sub('<[^>]*>',' ',str(x or '')))).strip()
def url_ok(url):
    try:return urlparse(str(url)).scheme=='https' and bool(urlparse(str(url)).hostname) and not urlparse(str(url)).username
    except ValueError:return False

def job(source,title,company,location,url,description='',**extra):
    if not title or not url_ok(url):return None
    return {'id':source+':'+hashlib.sha256(url.encode()).hexdigest()[:24],'source':source,'title':clean(title),'company':clean(company) or 'Company not supplied','location':clean(location) or 'Location not supplied','url':url,'description':clean(description)[:30000],'salary':'','type':'','date':'','workplace':'unknown','applicants':None,'applicantLabel':'Not supplied','verified':True,**extra}

def remote_type(location):
    return 'remote' if re.search(r'remote|worldwide|home.based',location,re.I) else 'hybrid' if re.search(r'hybrid',location,re.I) else 'onsite'

def jsonrpc(response):
    response.raise_for_status()
    if 'text/event-stream' in response.headers.get('content-type',''):
        found=[]
        for line in response.text.splitlines():
            if line.startswith('data:'):
                try:found.append(json.loads(line[5:].strip()))
                except ValueError:pass
        payload=next((x for x in reversed(found) if 'result' in x or 'error' in x),None)
        if payload is None:raise ValueError('No MCP result in event stream')
    else:payload=response.json()
    if payload.get('error'):raise ValueError('Provider rejected the MCP request')
    result=payload.get('result',{})
    if result.get('isError'):raise ValueError('Provider search returned an error')
    return result

async def mcp_search(client,board,search):
    headers={'Accept':'application/json, text/event-stream'}
    async def call(method,params,number=1):
        return jsonrpc(await client.post(board['endpoint'],json={'jsonrpc':'2.0','id':number,'method':method,'params':params},headers=headers))
    # Initialize for stateful MCP providers; reuse their exact session token.
    response=await client.post(board['endpoint'],json={'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'D3V Job Radar','version':'2.0'}}},headers=headers)
    if response.status_code==200:
        jsonrpc(response)
        if response.headers.get('mcp-session-id'):headers['Mcp-Session-Id']=response.headers['mcp-session-id']
        headers['MCP-Protocol-Version']='2025-03-26'
        await client.post(board['endpoint'],json={'jsonrpc':'2.0','method':'notifications/initialized'},headers=headers)
    tools=(await call('tools/list',{},2)).get('tools',[])
    tool=next((x for x in tools if x['name']=='search_jobs'),None)
    if not tool:raise ValueError('The provider did not advertise search_jobs')
    props=tool.get('inputSchema',{}).get('properties',{})
    candidates={'keyword':search['keywords'],'keywords':search['keywords'],'query':search['keywords'],'search':search['keywords'],'location':search['location'],'radius':25,'radius_unit':'mi','jobs_per_page':50,'page_number':1,'limit':50,'page':1,'posted_date':'SEVEN'}
    if search['workplace']!='all':candidates['workplace_types']={'remote':'Remote','hybrid':'Hybrid','onsite':'On-Site'}[search['workplace']]
    args={k:v for k,v in candidates.items() if k in props}
    for k in args:
        if props[k].get('type')=='array' and not isinstance(args[k],list):args[k]=[args[k]]
    missing=set(tool.get('inputSchema',{}).get('required',[]))-set(args)
    if missing:raise ValueError('Provider requires additional search options: '+', '.join(sorted(missing)))
    result=await call('tools/call',{'name':tool['name'],'arguments':args},3)
    candidates=[result.get('structuredContent')]
    for block in result.get('content',[]):
        if block.get('type')=='text':
            try:candidates.append(json.loads(block['text']))
            except ValueError:pass
    def find_rows(obj):
        if isinstance(obj,list):return obj
        if isinstance(obj,dict):
            for key in ['jobs','results','job_results','data','jobSearchResults','items']:
                if key in obj:
                    rows=find_rows(obj[key])
                    if rows is not None:return rows
        return None
    rows=next((r for c in candidates if (r:=find_rows(c)) is not None),None)
    if rows is None:raise ValueError('Provider response changed; use indexed search or import for this board.')
    jobs=[]
    for r in rows:
        if not isinstance(r,dict):continue
        company=r.get('company_name',r.get('companyName',r.get('company','')))
        if isinstance(company,dict):company=company.get('name','')
        loc=r.get('jobLocation',r.get('location',r.get('job_location','')))
        if isinstance(loc,dict):loc=loc.get('displayName',loc.get('display_name',loc.get('name',loc.get('city',''))))
        if isinstance(loc,list):loc=', '.join(str(x) for x in loc)
        url=r.get('detailsPageUrl') or r.get('url') or r.get('job_url') or r.get('jobUrl') or r.get('detailUrl') or r.get('job_detail_url') or r.get('apply_url')
        title=r.get('title') or r.get('job_title') or r.get('jobTitle')
        if not url:continue
        workplace=str(r.get('workplaceTypes',r.get('workplace_type',r.get('workplaceType','')))).lower()
        j=job(board['id'],title,company,loc,url,r.get('description',r.get('job_description',r.get('summary',''))),salary=clean(r.get('salary',r.get('salary_range',''))),date=clean(r.get('postedDate',r.get('posted_date',r.get('datePosted','')))),workplace='remote' if r.get('isRemote') or 'remote' in workplace else remote_type(clean(loc)),providerGuid=r.get('guid'),companyUrl=r.get('companyPageUrl'),verified=False,importMode='Search summary — load the full description or paste it before tailoring')
        if j:jobs.append(j)
    if rows and not jobs:raise ValueError('No valid job links in provider response')
    return jobs

async def indexed_search(client,board,search):
    key=os.getenv('BRAVE_SEARCH_API_KEY','')
    if not key:raise ValueError('Indexed search needs BRAVE_SEARCH_API_KEY; board search links and job import are available.')
    sites=' OR '.join('site:'+d for d in board.get('domains',[board['domain']]))
    q=f"({sites}) {search['keywords']} {search['location']} {search['workplace'] if search['workplace']!='all' else ''}"
    r=await client.get('https://api.search.brave.com/res/v1/web/search',params={'q':q,'count':20,'country':'US','freshness':'pm'},headers={'X-Subscription-Token':key})
    r.raise_for_status();rows=r.json().get('web',{}).get('results',[]);out=[]
    domains=[d.split('/')[0] for d in board.get('domains',[board['domain']])]
    for row in rows:
        host=(urlparse(row.get('url','')).hostname or '').lower()
        if not any(host==d or host.endswith('.'+d) for d in domains):continue
        j=job(board['id'],row.get('title'),'Company not supplied','Location not supplied',row['url'],row.get('description',''),verified=False,importMode='Indexed result — paste full job description before tailoring')
        if j:out.append(j)
    return out

async def ashby_jobs(client,board):
    # Fixed provider endpoint and board slug; no arbitrary-URL fetching.
    response=await client.get('https://api.ashbyhq.com/posting-api/job-board/'+board['board'],params={'includeCompensation':'true'})
    response.raise_for_status();payload=response.json()
    if not isinstance(payload.get('jobs'),list):raise ValueError('Ashby response changed')
    out=[]
    for row in payload['jobs']:
        if row.get('isListed') is False:continue
        kind=str(row.get('workplaceType') or '').lower()
        workplace={'remote':'remote','hybrid':'hybrid','onsite':'onsite','on-site':'onsite'}.get(kind,'unknown')
        locations=[clean(row.get('location'))]+[clean(x.get('location')) for x in row.get('secondaryLocations',[]) if isinstance(x,dict)]
        compensation=row.get('compensation') or {}
        salary=clean(compensation.get('scrapeableCompensationSalarySummary') or compensation.get('compensationTierSummary')) if isinstance(compensation,dict) else ''
        value=job(board['id'],row.get('title'),board['name'],', '.join(x for x in locations if x),row.get('jobUrl'),row.get('descriptionPlain') or row.get('descriptionHtml'),salary=salary,type=clean(row.get('employmentType')),date=clean(row.get('publishedAt')),workplace=workplace,applicationUrl=row.get('applyUrl') if url_ok(row.get('applyUrl')) else None)
        if value:out.append(value)
    return out

async def fetch_board(client,b,s):
    if b['mode']=='manual':raise ValueError('Source unavailable during review; use its original link or import a job manually.')
    if b['mode'] in ('wwr','remoteok','lever'):return await public_jobs(client,b),False
    if b['mode']=='ashby':return await ashby_jobs(client,b),True
    if b['mode']=='indexed':return await indexed_search(client,b,s),False
    if b['mode']=='mcp':return await mcp_search(client,b,s),False
    if b['id']=='remotive':
        r=await client.get('https://remotive.com/api/remote-jobs');r.raise_for_status();payload=r.json();out=[]
        if not isinstance(payload.get('jobs'),list):raise ValueError('Source response changed')
        for row in payload['jobs']:
            j=job(b['id'],row.get('title'),row.get('company_name'),row.get('candidate_required_location'),row.get('url'),row.get('description'),salary=clean(row.get('salary')),type=clean(row.get('job_type')),date=clean(row.get('publication_date')),workplace='remote')
            if j:out.append(j)
        return out,True
    if b['id']=='himalayas':
        r=await client.get('https://himalayas.app/jobs/api/search',params={'q':s['keywords'],'country':'US','sort':'recent'});r.raise_for_status();payload=r.json();out=[]
        if not isinstance(payload.get('jobs'),list):raise ValueError('Source response changed')
        for row in payload['jobs']:
            j=job(b['id'],row.get('title'),row.get('companyName'),', '.join(row.get('locationRestrictions') or ['Worldwide']),row.get('applicationLink'),row.get('description',row.get('excerpt')),salary=f"{row.get('currency','')} {row.get('minSalary') or ''} - {row.get('maxSalary') or ''} {row.get('salaryPeriod','')}" if row.get('minSalary') else '',type=clean(row.get('employmentType')),date=str(row.get('pubDate','')),workplace='remote',expires=row.get('expiryDate'))
            if j:out.append(j)
        return out,False
    r=await client.get(f"https://boards-api.greenhouse.io/v1/boards/{b.get('board',b['id'])}/jobs",params={'content':'true'});r.raise_for_status();payload=r.json();out=[]
    if not isinstance(payload.get('jobs'),list):raise ValueError('Source response changed')
    for row in payload['jobs']:
        loc=clean(row.get('location',{}).get('name'))
        j=job(b['id'],row.get('title'),b['name'],loc,row.get('absolute_url'),row.get('content'),date=clean(row.get('updated_at')),workplace=remote_type(loc),applicationUrl=f"https://job-boards.greenhouse.io/{b.get('board',b['id'])}/jobs/{row['id']}" if str(row.get('id','')).isdigit() else None)
        if j:out.append(j)
    return out,True

SCANNING=set()
COLLECTION_LOCK=asyncio.Lock()
def scan_running():return current_workspace() in SCANNING

async def scan_sources():
    ident=current_workspace()
    if ident in SCANNING:return {'running':True}
    SCANNING.add(ident);results=[]
    try:
        search=get_setting('search',DEFAULT_SEARCH)
        async with httpx.AsyncClient(timeout=httpx.Timeout(25,connect=8),follow_redirects=True,headers={'User-Agent':'D3VJobRadar/2.3 (personal job search)','Accept':'application/json'}) as client:
            for b in BOARDS:
                now=time.time()
                fp=hashlib.sha256(json.dumps({k:search[k] for k in ['keywords','location','workplace']},sort_keys=True).encode()).hexdigest() if b['mode'] in ('mcp','indexed') or b['id']=='himalayas' else ''
                with db() as c:
                    c.execute('INSERT OR IGNORE INTO source_runs(id) VALUES(?)',(b['id'],))
                    row=c.execute('SELECT * FROM source_runs WHERE id=?',(b['id'],)).fetchone()
                    cooldown=300 if row['error'] else 43200
                    if row['lease']>now or (row['fingerprint']==fp and row['checked']>now-cooldown) or row['checked']>now-60:results.append({'id':b['id'],'cached':True});continue
                    c.execute('UPDATE source_runs SET checked=?,lease=?,fingerprint=? WHERE id=?',(now,now+180,fp,b['id']))
                try:
                    # Same public feed/query is fetched once for all beta workspaces.
                    cache_key=hashlib.sha256(json.dumps([b,fp,bool(os.getenv('BRAVE_SEARCH_API_KEY'))],sort_keys=True).encode()).hexdigest()
                    async with COLLECTION_LOCK:
                        cached=cached_public_feed(cache_key)
                        if cached is not None:jobs,snapshot=cached
                        else:
                            try:jobs,snapshot=await fetch_board(client,b,search)
                            except Exception:
                                if b['mode']!='mcp' or not os.getenv('BRAVE_SEARCH_API_KEY'):raise
                                jobs=await indexed_search(client,b,search);snapshot=False
                            cache_public_feed(cache_key,jobs,snapshot)
                    upsert_jobs(b['id'],jobs,snapshot)
                    with db() as c:c.execute("UPDATE source_runs SET success=?,count=?,error='',lease=0 WHERE id=?",(time.time(),len(jobs),b['id']))
                    results.append({'id':b['id'],'count':len(jobs)})
                except Exception as e:
                    # Never expose response bodies, keys or headers to the UI.
                    message=str(e) if isinstance(e,ValueError) else f'{type(e).__name__}: could not retrieve this source. Existing jobs were retained.'
                    with db() as c:c.execute('UPDATE source_runs SET error=?,lease=0 WHERE id=?',(message[:400],b['id']))
                    results.append({'id':b['id'],'error':message[:400]})
    finally:SCANNING.discard(ident)
    return {'results':results}

def source_status():
    search=get_setting('search',DEFAULT_SEARCH)
    with db() as c:rows={r['id']:dict(r) for r in c.execute('SELECT * FROM source_runs')}
    return [{**{k:v for k,v in b.items() if k!='endpoint'},**rows.get(b['id'],{}),'searchUrl':'https://www.google.com/search?q='+quote_plus(f"site:{b.get('domain',urlparse(b['url']).netloc)} {search['keywords']} {search['location']} {search['workplace']}"),'application':source_audit(b['id']),'automatic':b['mode']!='manual' and (b['mode']!='indexed' or bool(os.getenv('BRAVE_SEARCH_API_KEY')))} for b in BOARDS]

async def public_jobs(client,board):
    """Read documented public feeds; no private submissions or account scraping."""
    mode=board['mode'];ident=board['id'];out=[]
    if mode=='wwr':
        import xml.etree.ElementTree as ET
        response=await client.get('https://weworkremotely.com/remote-jobs.rss');response.raise_for_status()
        if len(response.content)>8000000:raise ValueError('RSS response too large')
        root=ET.fromstring(response.content)
        if root.tag!='rss' or root.find('channel') is None:raise ValueError('RSS response changed')
        for row in root.findall('./channel/item'):
            title=clean(row.findtext('title'));company,sep,role=title.partition(':')
            j=job(ident,role.strip() if sep else title,company if sep else 'Company not supplied',row.findtext('region') or 'Remote — verify geographic eligibility',row.findtext('link'),row.findtext('description'),workplace='remote',date=clean(row.findtext('pubDate')))
            if j:out.append(j)
    elif mode=='remoteok':
        response=await client.get('https://remoteok.com/api');response.raise_for_status();rows=response.json()
        if not isinstance(rows,list):raise ValueError('Remote OK response changed')
        for row in rows:
            if not isinstance(row,dict) or not row.get('position'):continue
            j=job(ident,row.get('position'),row.get('company'),row.get('location') or 'Remote — verify geographic eligibility',row.get('url'),row.get('description'),workplace='remote',date=clean(row.get('date')),salary=f"{row.get('salary_min') or ''} – {row.get('salary_max') or ''}" if row.get('salary_min') else '')
            if j:out.append(j)
    elif mode=='lever':
        host='api.eu.lever.co' if board.get('region')=='eu' else 'api.lever.co'
        response=await client.get('https://'+host+'/v0/postings/'+board['board'],params={'mode':'json'});response.raise_for_status();rows=response.json()
        if not isinstance(rows,list):raise ValueError('Lever response changed')
        for row in rows:
            cats=row.get('categories') or {};parts=[row.get('descriptionPlain') or row.get('description','')]
            for group in row.get('lists',[]):parts.extend([group.get('text',''),group.get('content','')])
            parts.append(row.get('additionalPlain') or row.get('additional',''))
            kind=str(row.get('workplaceType') or '').lower()
            j=job(ident,row.get('text'),board['name'],cats.get('location'),row.get('hostedUrl'),' '.join(parts),workplace=kind if kind in ('remote','hybrid','onsite') else 'unknown',type=clean(cats.get('commitment')),applicationUrl=row.get('applyUrl') if url_ok(row.get('applyUrl')) else None)
            if j:out.append(j)
    return out
