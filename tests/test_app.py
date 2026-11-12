import io,json,sqlite3,zipfile,asyncio,time
import pytest
from fastapi.testclient import TestClient
from cryptography.fernet import Fernet
from radar.app import app
from radar.store import db,get_setting,put_setting,DEFAULT_SEARCH,get_job,upsert_jobs
from radar.documents import extract,prepare_resume,cover_letter,analyze,docx_bytes,pdf_bytes
from radar import sources

HEADERS={'Authorization':'Bearer test-token-for-fixtures-only-32-chars','Origin':'http://testserver'}
RESUME='''Test Candidate
candidate@example.test
Albany, New York

PROFESSIONAL EXPERIENCE
Systems Administrator, Example Company 2020-2025
- Managed Active Directory and Microsoft 365 for 15 users and resolved Windows support tickets.
- Organized warehouse equipment and maintained inventory records for the team.
- Automated account maintenance using PowerShell and deployed Intune configuration policies.
EDUCATION
Example College 2018
CERTIFICATIONS
CompTIA A+
'''
JOB={'title':'IT Support Technician','company':'Sample Employer','location':'Remote, United States','url':'https://example.test/jobs/support','description':'Provide Windows and Active Directory support, troubleshoot Microsoft 365 and Intune, use PowerShell, and manage Azure services. We require Kubernetes experience for this role.','source':'manual','workplace':'remote','applicants':None}

@pytest.fixture
def client():
    with TestClient(app,headers=HEADERS) as c:yield c

def test_auth_and_origin(client):
    assert client.get('/health',headers={'Authorization':''}).status_code==200
    assert client.get('/api/workspace',headers={'Authorization':''}).status_code==401
    assert client.put('/api/profile',headers={'Origin':'https://evil.test'},json={'name':'Test'}).status_code==403
    assert client.get('/api/workspace').status_code==200

def upload(client,kind,text,name='resume.txt'):
    r=client.post('/api/documents',data={'kind':kind},files={'file':(name,text.encode(),'text/plain')});assert r.status_code==200,r.text;return r.json()

def test_upload_encryption_and_original(client):
    d=upload(client,'resume',RESUME)
    with db() as c:payload=c.execute('SELECT payload FROM documents WHERE id=?',(d['id'],)).fetchone()['payload']
    assert b'candidate@example.test' not in payload
    assert client.get('/api/documents/'+d['id']+'/original').content==RESUME.encode()
    assert client.get('/api/documents/'+d['id']).json()['text']==RESUME.strip()
    assert client.post('/api/documents',data={'kind':'resume'},files={'file':('x.exe',b'A'*100)}).status_code==400
    assert client.post('/api/documents',data={'kind':'resume'},files={'file':('x.txt',b'A'*(8*1024*1024+1))}).status_code==400

def test_tailoring_followup_versions_and_exports(client):
    upload(client,'resume',RESUME)
    upload(client,'cover','Dear Hiring Team,\n\nI am applying for {{role}} at {{company}}. My background includes {{relevant_skills}}.\n{{evidence}}\n\nSincerely,\n{{name}}','cover.txt')
    j=client.post('/api/jobs',json=JOB).json()['job']
    result=client.post('/api/jobs/'+j['id']+'/prepare');assert result.status_code==200,result.text
    drafts=result.json()['drafts'];assert len(drafts)==2
    resume=next(d for d in drafts if d['kind']=='resume');cover=next(d for d in drafts if d['kind']=='cover')
    assert 'Kubernetes' not in resume['text'];assert 'Kubernetes' not in cover['text']
    assert 'Example Company 2020-2025' in resume['text']
    assert 'Azure' in resume['report']['missing']
    assert '{{company}}' not in cover['text'] and 'Sample Employer' in cover['text']
    assert client.post('/api/jobs/'+j['id']+'/prepare').json()['drafts'][0]['id'] in [d['id'] for d in drafts]
    for fmt in ['docx','pdf','txt']:
        r=client.get('/api/drafts/'+resume['id']+'/download',params={'format':fmt});assert r.status_code==200 and len(r.content)>200
        if fmt=='docx':assert zipfile.is_zipfile(io.BytesIO(r.content))
        if fmt=='pdf':assert r.content.startswith(b'%PDF')
    assert client.post('/api/jobs/'+j['id']+'/followup').status_code==400
    r=client.put('/api/applications/'+j['id'],json={'status':'applied','notes':'Private interview note'});assert r.status_code==200 and r.json()['followup']>time.time()
    letter=client.post('/api/jobs/'+j['id']+'/followup').json();assert 'Sample Employer' in letter['text']
    with db() as c:
        note=c.execute('SELECT notes FROM applications WHERE job_id=?',(j['id'],)).fetchone()['notes'];assert b'Private interview note' not in note
    upsert_jobs('manual',[],snapshot=True)
    w=client.get('/api/workspace').json();assert any(a['job_id']==j['id'] for a in w['applications']);assert any(x['id']==j['id'] for x in w['jobs'])
    before=resume['text'];edited=before+'\nUser reviewed this version.'
    assert client.put('/api/drafts/'+resume['id'],json={'text':edited,'reviewed':True}).status_code==200
    assert client.get('/api/drafts/'+resume['id']+'/download',params={'format':'txt'}).text==edited

def test_sensitive_profile_excluded(client):
    profile={'name':'Test Candidate','email':'candidate@example.test','location':'Albany, NY','veteran':False,'disability':False,'needs_sponsorship':False,'felony':False,'us_citizen':True,'authorized_us':True}
    assert client.put('/api/profile',json=profile).status_code==200
    pack=client.get('/api/profile/answers').json();assert pack['us_citizen'] and not pack['needs_sponsorship']
    upload(client,'resume',RESUME)
    j=client.post('/api/jobs',json={**JOB,'url':'https://example.test/jobs/other'}).json()['job']
    texts=' '.join(d['text'] for d in client.post('/api/jobs/'+j['id']+'/prepare').json()['drafts'])
    assert 'disability' not in texts.lower() and 'felony' not in texts.lower() and 'veteran' not in texts.lower()

def test_invalid_import_and_summary(client):
    assert client.post('/api/jobs',json={**JOB,'url':'javascript:alert(1)'}).status_code==400
    assert client.post('/api/jobs',json={**JOB,'applicants':-1}).status_code==422
    j=sources.job('linkedin','Example role','Example','Unknown','https://linkedin.com/jobs/view/test','Only an index snippet',verified=False)
    upsert_jobs('linkedin',[j]);assert client.post('/api/jobs/'+j['id']+'/prepare').status_code==400

def test_fact_preservation_and_docx_extraction():
    text,report=prepare_resume(RESUME,JOB)
    for line in RESUME.splitlines():
        if line.strip():assert line in text
    assert report['coverage'] is not None and report['label'].startswith('Keyword')
    raw=docx_bytes(RESUME);read=extract('resume.docx',raw)
    assert 'Example Company 2020-2025' in read
    pdf=pdf_bytes(RESUME);assert 'Test Candidate' in extract('resume.pdf',pdf)

@pytest.mark.anyio
async def test_source_failure_retains_snapshot(monkeypatch,client):
    j=sources.job('remotive','Support','Example','Remote','https://remotive.com/jobs/test','A valid job description for this test only.')
    upsert_jobs('remotive',[j]);original=sources.BOARDS;monkeypatch.setattr(sources,'BOARDS',[original[0]])
    async def bad(*args):raise ValueError('Source unavailable in test')
    monkeypatch.setattr(sources,'fetch_board',bad)
    with db() as c:c.execute("DELETE FROM source_runs WHERE id='remotive'")
    result=await sources.scan_sources();assert result['results'][0]['error'];assert get_job(j['id'])['active']
    with db() as c:assert c.execute("SELECT lease FROM source_runs WHERE id='remotive'").fetchone()['lease']==0

@pytest.fixture
def anyio_backend():return 'asyncio'

def test_migration(client):
    old={'jobs':[{'source':'legacy','title':'Legacy role','company':'Example','url':'https://example.test/legacy','location':'Remote','description':'Legacy description'}],'applications':[{'id':'example:legacyrole:remote','status':'applied','notes':'Saved history'}]}
    r=client.post('/api/migrate',files={'file':('migration.json',json.dumps(old).encode(),'application/json')});assert r.status_code==200,r.text;assert r.json()['applications']==1

def test_access_signature_audience_and_allowlist(client,monkeypatch):
    import jwt
    import radar.security as security
    from cryptography.hazmat.primitives.asymmetric import rsa
    from types import SimpleNamespace
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    monkeypatch.setattr(security,'MODE','cloudflare');monkeypatch.setattr(security,'TEAM','test.cloudflareaccess.com');monkeypatch.setattr(security,'AUD','expected-audience');monkeypatch.setattr(security,'ALLOWED',{'candidate@example.test'})
    class Keys:
        def get_signing_key_from_jwt(self,token):return SimpleNamespace(key=key.public_key())
    monkeypatch.setattr(security,'CLIENT',Keys())
    base={'iss':'https://test.cloudflareaccess.com','aud':['expected-audience'],'email':'candidate@example.test','iat':int(time.time()),'exp':int(time.time())+300}
    def access(claims):return {'Cf-Access-Jwt-Assertion':jwt.encode(claims,key,algorithm='RS256')}
    assert client.get('/api/workspace',headers=access(base)).status_code==200
    assert client.get('/api/workspace',headers=access({**base,'aud':['wrong-audience']})).status_code==401
    assert client.get('/api/workspace',headers=access({**base,'email':'other@example.test'})).status_code==401
    assert client.get('/api/workspace',headers=access({**base,'exp':int(time.time())-1})).status_code==401
    assert client.get('/api/workspace',headers={'Cf-Access-Authenticated-User-Email':'candidate@example.test'}).status_code==401
    other=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    assert client.get('/api/workspace',headers={'Cf-Access-Jwt-Assertion':jwt.encode(base,other,algorithm='RS256')}).status_code==401
    monkeypatch.setattr(security,'AUD','')
    with pytest.raises(RuntimeError):security.validate_config()

def test_due_followups_are_drafted_once(client):
    from radar.drafts import draft_due_followups
    j=client.post('/api/jobs',json={**JOB,'url':'https://example.test/jobs/followup-due'}).json()['job']
    client.put('/api/applications/'+j['id'],json={'status':'applied','followup':time.time()-10})
    draft_due_followups();draft_due_followups()
    found=client.get('/api/jobs/'+j['id']+'/drafts').json()['drafts']
    assert len([d for d in found if d['kind']=='followup'])==1

@pytest.mark.anyio
async def test_dice_response_schema(monkeypatch,client):
    import httpx
    board=next(b for b in sources.BOARDS if b['id']=='dice')
    responses=[{'result':{'protocolVersion':'2025-03-26'}},{}, {'result':{'tools':[{'name':'search_jobs','inputSchema':{'properties':{'keyword':{'type':'string'},'workplace_types':{'type':'array'},'location':{'type':'string'}},'required':['keyword']}}]}}, {'result':{'structuredContent':{'data':[{'guid':'guid-test','title':'IT Support','companyName':'Example','jobLocation':{'displayName':'Remote, US'},'detailsPageUrl':'https://www.dice.com/job-detail/test','companyPageUrl':'https://www.dice.com/company/test','summary':'A search summary','isRemote':True}]}}}]
    async def handler(request):
        r=responses.pop(0);return httpx.Response(200,json=r,request=request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        rows=await sources.mcp_search(c,board,DEFAULT_SEARCH)
    assert len(rows)==1 and rows[0]['providerGuid']=='guid-test' and rows[0]['workplace']=='remote'
    assert not rows[0]['verified'] and rows[0]['companyUrl'].endswith('/company/test')

@pytest.mark.anyio
async def test_index_results_keep_unknowns(monkeypatch,client):
    import httpx
    monkeypatch.setenv('BRAVE_SEARCH_API_KEY','mock-key')
    board=next(b for b in sources.BOARDS if b['id']=='linkedin')
    async def handler(request):
        assert request.headers['X-Subscription-Token']=='mock-key'
        return httpx.Response(200,json={'web':{'results':[{'title':'Support','url':'https://www.linkedin.com/jobs/view/1','description':'Indexed summary'},{'title':'Not LinkedIn','url':'https://linkedin.com.evil.test/1'}]}},request=request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:rows=await sources.indexed_search(c,board,DEFAULT_SEARCH)
    assert len(rows)==1 and rows[0]['applicants'] is None and not rows[0]['verified'] and rows[0]['workplace']=='unknown'

@pytest.mark.anyio
async def test_cache_respects_changed_queries(monkeypatch,client):
    b=next(b for b in sources.BOARDS if b['id']=='himalayas');monkeypatch.setattr(sources,'BOARDS',[b]);calls=[]
    async def fake(*args):calls.append(1);return [],False
    monkeypatch.setattr(sources,'fetch_board',fake)
    with db() as c:c.execute("DELETE FROM source_runs WHERE id='himalayas'")
    await sources.scan_sources();await sources.scan_sources();assert len(calls)==1
    put_setting('search',{**DEFAULT_SEARCH,'keywords':'Systems Administrator'})
    with db() as c:c.execute("UPDATE source_runs SET checked=? WHERE id='himalayas'",(time.time()-61,))
    await sources.scan_sources();assert len(calls)==2
    put_setting('search',DEFAULT_SEARCH)

def test_saved_to_applied_gets_followup(client):
    j=client.post('/api/jobs',json={**JOB,'url':'https://example.test/jobs/saved-transition'}).json()['job']
    client.put('/api/applications/'+j['id'],json={'status':'saved'})
    r=client.put('/api/applications/'+j['id'],json={'status':'applied','applied':None,'followup':None})
    assert r.json()['applied'] and r.json()['followup']>time.time()

def test_added_sources_registered(client):
    boards={b['id']:b for b in sources.BOARDS}
    assert {'teal','greenhouse','ashby','jobleads','jobilize'}<=set(boards)
    assert boards['ashby']['board']=='Ashby' and boards['ashby']['mode']=='ashby'
    assert boards['greenhouse']['url']=='https://www.greenhouse.com/for-job-seekers'
    assert len([b for b in sources.BOARDS if b['id']=='jobleads'])==1
    for key in ['teal','greenhouse','ashby','jobleads','jobilize']:
        r=client.post('/api/jobs',json={**JOB,'source':key,'url':'https://example.test/'+key})
        assert r.status_code==200,r.text

@pytest.mark.anyio
async def test_ashby_public_feed_maps_hybrid(monkeypatch,client):
    import httpx
    board=next(b for b in sources.BOARDS if b['id']=='ashby')
    rows=[{'title':'Support Engineer','location':'United States','workplaceType':'Hybrid','isRemote':True,'isListed':True,'descriptionPlain':'Support customers and troubleshoot systems.','jobUrl':'https://jobs.ashbyhq.com/Ashby/123','applyUrl':'https://jobs.ashbyhq.com/Ashby/123/application','compensation':{'scrapeableCompensationSalarySummary':'$70,000 - $90,000'}},{'title':'Hidden','isListed':False,'jobUrl':'https://jobs.ashbyhq.com/Ashby/hidden'},{'title':'No valid URL','jobUrl':'javascript:alert(1)'}]
    async def handler(request):
        assert '/job-board/Ashby' in str(request.url)
        return httpx.Response(200,json={'jobs':rows},request=request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:jobs,snapshot=await sources.fetch_board(c,board,DEFAULT_SEARCH)
    assert snapshot and len(jobs)==1
    assert jobs[0]['workplace']=='hybrid' and jobs[0]['verified']
    assert jobs[0]['salary']=='$70,000 - $90,000'
    assert jobs[0]['applicationUrl'].endswith('/application')

@pytest.mark.anyio
async def test_greenhouse_discovery_domains(monkeypatch,client):
    import httpx
    monkeypatch.setenv('BRAVE_SEARCH_API_KEY','fixture')
    board=next(b for b in sources.BOARDS if b['id']=='greenhouse')
    async def handler(request):
        assert 'site:boards.greenhouse.io' in request.url.params['q']
        return httpx.Response(200,json={'web':{'results':[{'title':'Support','url':'https://boards.greenhouse.io/company/jobs/1'},{'title':'Engineer','url':'https://job-boards.greenhouse.io/company/jobs/2'},{'title':'Spoof','url':'https://boards.greenhouse.io.evil.test/3'}]}},request=request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:rows=await sources.indexed_search(c,board,DEFAULT_SEARCH)
    assert len(rows)==2 and all(not r['verified'] for r in rows)

def test_apply_defaults_now_but_can_edit_date(client):
    j=client.post('/api/jobs',json={**JOB,'url':'https://example.test/default-applied-date'}).json()['job']
    before=time.time()
    created=client.put('/api/applications/'+j['id'],json={'status':'applied'}).json()
    assert before<=created['applied']<=time.time()
    chosen=before-3*86400
    changed=client.put('/api/applications/'+j['id'],json={'status':'applied','applied':chosen}).json()
    assert changed['applied']==chosen


@pytest.mark.anyio
async def test_reyrey_indexed_search_keeps_only_job_details(monkeypatch):
    import httpx
    monkeypatch.setenv('BRAVE_SEARCH_API_KEY','fixture-key')
    board=next(b for b in sources.BOARDS if b['id']=='reyrey')
    listing=board['url']+'/12345'

    def handler(request):
        assert 'site:reyrey.com/company/careers/job-openings/' in request.url.params['q']
        return httpx.Response(200,json={'web':{'results':[
            {'title':'Example technician','url':listing},
            {'title':'Openings directory','url':board['url']},
            {'title':'Careers','url':'https://www.reyrey.com/company/careers'},
            {'title':'Lookalike','url':'https://reyrey.com.example.com/company/careers/job-openings/12345'},
        ]}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        jobs=await sources.indexed_search(client,board,DEFAULT_SEARCH)
    assert [job['url'] for job in jobs]==[listing]
    assert jobs[0]['company']=='Reynolds and Reynolds'
    assert jobs[0]['verified'] is False
