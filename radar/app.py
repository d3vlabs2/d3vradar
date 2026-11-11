import asyncio, base64, hashlib, io, json, os, time, uuid
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, ConfigDict
from . import members,store
from . import sources
from .apply import application_options
from .importer import fetch_details
from .store import db,init,seal,unseal,get_setting,put_setting,get_job,upsert_jobs,DEFAULT_PROFILE,DEFAULT_SEARCH
from .security import guard,validate_config
from . import security
from .store import configure_workspaces,workspace_context,ensure_workspace,workspace_emails
from .documents import extract,MAX_SIZE,docx_bytes,pdf_bytes
from .drafts import prepare,prepare_followup,drain_queue,draft_due_followups

async def maintain_workspaces():
    allowed=security.allowed_emails()
    for email in workspace_emails(allowed):
        with workspace_context(email):
            try:
                await sources.scan_sources()
                if get_setting('search',DEFAULT_SEARCH).get('auto_prepare'):
                    await asyncio.to_thread(drain_queue,5)
                await asyncio.to_thread(draft_due_followups,5)
            except asyncio.CancelledError:raise
            except Exception:
                # One workspace failure must not interrupt other users' maintenance.
                pass

async def maintenance():
    while True:
        try:await maintain_workspaces()
        except asyncio.CancelledError:raise
        except Exception:pass
        await asyncio.sleep(30)

@asynccontextmanager
async def lifespan(app):
    validate_config()
    sources.COLLECTION_LOCK=asyncio.Lock()
    configure_workspaces(security.MODE,security.ALLOWED,os.getenv('RADAR_OWNER_EMAIL',''))
    from .store import OWNER_EMAIL
    ensure_workspace(OWNER_EMAIL)
    task=None
    if os.getenv('RADAR_SCHEDULER','true')=='true':task=asyncio.create_task(maintenance())
    yield
    for scan_task in list(running_tasks):scan_task.cancel()
    if running_tasks:await asyncio.gather(*list(running_tasks),return_exceptions=True)
    if task:
        task.cancel()
        try:await task
        except asyncio.CancelledError:pass

app=FastAPI(title='D3V Job Radar',version='2.8.1',lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
app.middleware('http')(guard)
@app.exception_handler(ValueError)
async def value_error(request,exc):return JSONResponse({'detail':str(exc)},400)
@app.get('/health')
def health():return {'status':'ok','version':'2.8.1'}

class Profile(BaseModel):
    name:str=Field(max_length=150);email:str=Field(default='',max_length=250);location:str=Field(default='',max_length=150)
    home_address:str=Field(default='',max_length=300)
    veteran:bool=False;disability:bool=False;needs_sponsorship:bool=False;felony:bool=False;us_citizen:bool=False;authorized_us:bool=False
    @field_validator('home_address')
    @classmethod
    def trim_home_address(cls,value):return value.strip()
class SearchProfile(BaseModel):
    keywords:str=Field(min_length=2,max_length=150);location:str=Field(max_length=150);workplace:str='remote';auto_prepare:bool=True;followup_days:int=Field(default=7,ge=1,le=90)
class ImportedJob(BaseModel):
    title:str=Field(min_length=2,max_length=300);company:str=Field(min_length=1,max_length=250);location:str=Field(default='',max_length=250);url:str=Field(max_length=2000)
    officeAddress:str=Field(default='',max_length=300)
    description:str=Field(min_length=80,max_length=60000);source:str='manual';workplace:str='unknown';salary:str=Field(default='',max_length=200);applicants:int|None=Field(default=None,ge=0,le=10000000);applicantLabel:str=Field(default='Not supplied',max_length=200)
class JobImport(ImportedJob):
    save_to_saved:bool=True
    notes:str=Field(default='',max_length=20000)

class ApplicationUpdate(BaseModel):
    status:str;notes:str=Field(default='',max_length=20000);followup:float|None=None;applied:float|None=None
class DraftUpdate(BaseModel):
    text:str=Field(min_length=30,max_length=150000);reviewed:bool=False
class TextUpdate(BaseModel):
    text:str=Field(min_length=30,max_length=150000)

@app.get('/api/workspace')
def workspace(request:Request):
    with db() as c:
        jobs=[{**json.loads(r['payload']),'active':bool(r['active']) and not (json.loads(r['payload']).get('expires') and float(json.loads(r['payload'])['expires'])<time.time()),'firstSeen':r['first_seen']} for r in c.execute('SELECT * FROM jobs ORDER BY first_seen DESC LIMIT 3000')]
        applications=[{**{k:r[k] for k in ['job_id','status','applied','followup','updated']},'notes':unseal(r['notes'])} for r in c.execute('SELECT * FROM applications')]
        documents=[{k:r[k] for k in ['id','kind','name','created','active']} for r in c.execute('SELECT * FROM documents ORDER BY created DESC')]
        drafts=[{k:r[k] for k in ['id','job_id','kind','created','approved']} for r in c.execute('SELECT id,job_id,kind,created,approved FROM drafts ORDER BY created DESC')]
        queue={r['status']:r['n'] for r in c.execute('SELECT status,COUNT(*) n FROM queue GROUP BY status')}
    return {'identity':{'email':request.state.identity,'privateWorkspace':True,'mode':security.MODE,'isOwner':security.MODE=='cloudflare' and request.state.identity==store.OWNER_EMAIL},'jobs':jobs,'applications':applications,'documents':documents,'drafts':drafts,'sources':sources.source_status(),'profile':get_setting('profile',DEFAULT_PROFILE),'search':get_setting('search',DEFAULT_SEARCH),'scanRunning':sources.scan_running(),'queue':queue,'scheduler':os.getenv('RADAR_SCHEDULER','true')=='true','indexedSearch':bool(os.getenv('BRAVE_SEARCH_API_KEY')),'mapsEmbedKey':os.getenv('GOOGLE_MAPS_EMBED_API_KEY','').strip()}

def require_owner(request:Request):
    if security.MODE!='cloudflare' or request.state.identity!=store.OWNER_EMAIL:
        raise HTTPException(403,'Only the workspace owner can manage users.')

class MemberInvite(BaseModel):
    model_config=ConfigDict(extra='forbid')
    email:str=Field(min_length=3,max_length=254)

class MemberAccess(BaseModel):
    model_config=ConfigDict(extra='forbid')
    enabled:bool

@app.get('/api/admin/users')
def admin_users(request:Request):
    require_owner(request)
    return {'users':members.list_members(security.ALLOWED),'cloudflarePolicyManaged':False}

@app.post('/api/admin/users')
def admin_invite(request:Request,p:MemberInvite):
    require_owner(request)
    return {'user':members.add_member(p.email,security.ALLOWED),'cloudflarePolicyManaged':False}

@app.put('/api/admin/users/{member_id}')
def admin_access(request:Request,member_id:str,p:MemberAccess):
    require_owner(request)
    return {'user':members.set_enabled(member_id,p.enabled,security.ALLOWED)}

@app.put('/api/profile')
def profile_save(p:Profile):
    put_setting('profile',p.model_dump());put_setting('profile_reviewed',True);return {'ok':True}
@app.get('/api/profile/answers')
def answers():
    if not get_setting('profile_reviewed',False):raise ValueError('Review every answer in Profile and save it before exporting an answer pack.')
    p=get_setting('profile',DEFAULT_PROFILE)
    return {'schema':1,'veteran':p['veteran'],'disability':p['disability'],'needs_sponsorship':p['needs_sponsorship'],'felony':p['felony'],'us_citizen':p['us_citizen'],'authorized_us':p['authorized_us']}
@app.put('/api/search')
def search_save(s:SearchProfile):
    if s.workplace not in ('all','remote','hybrid','onsite'):raise ValueError('Unknown workplace filter')
    old=get_setting('search',DEFAULT_SEARCH)
    value={**s.model_dump(),'scan_hours':12};put_setting('search',value)
    if old.get('keywords')!=s.keywords:
        with db() as c:c.execute("UPDATE queue SET status='pending',error='' WHERE status IN ('skipped','error')")
    return {'ok':True,'nextScan':'Changed queries are collected on the next scan. Repeated queries keep a 12-hour cache; one-minute minimum between source attempts.'}
@app.post('/api/scan')
async def scan():
    if sources.scan_running():return {'running':True}
    task=asyncio.create_task(sources.scan_sources())
    # Keep a strong reference until the background scan is finished.
    running_tasks.add(task);task.add_done_callback(running_tasks.discard)
    return {'running':True}
running_tasks=set()

@app.post('/api/documents')
async def upload_document(kind:str=Form(...),file:UploadFile=File(...)):
    if kind not in ('resume','cover'):raise ValueError('Choose resume or cover letter')
    data=await file.read(MAX_SIZE+1)
    name=Path((file.filename or 'document').replace('\\','/')).name[:180]
    try:text=await asyncio.to_thread(extract,name,data)
    except ValueError:raise
    except Exception:raise ValueError('This document could not be read. Upload a readable PDF, DOCX, or TXT file.')
    id=uuid.uuid4().hex;payload={'id':id,'text':text,'original':base64.b64encode(data).decode(),'sha256':hashlib.sha256(data).hexdigest()}
    with db() as c:
        c.execute('UPDATE documents SET active=0 WHERE kind=?',(kind,))
        c.execute('INSERT INTO documents VALUES(?,?,?,?,?,1)',(id,kind,name,seal(payload),time.time()))
        c.execute("UPDATE queue SET status='pending',error='' WHERE status IN ('done','error')")
    return {'id':id,'text':text,'name':name,'kind':kind}
@app.get('/api/documents/{id}')
def document_read(id:str):
    with db() as c:r=c.execute('SELECT * FROM documents WHERE id=?',(id,)).fetchone()
    if not r:raise HTTPException(404,'Document not found')
    value=unseal(r['payload']);return {'id':id,'name':r['name'],'kind':r['kind'],'active':bool(r['active']),'text':value['text']}
@app.put('/api/documents/{id}')
def document_text(id:str,p:TextUpdate):
    with db() as c:
        r=c.execute('SELECT * FROM documents WHERE id=?',(id,)).fetchone()
        if not r:raise HTTPException(404,'Document not found')
        value=unseal(r['payload']);value['text']=p.text
        c.execute('UPDATE documents SET payload=? WHERE id=?',(seal(value),id))
        c.execute("UPDATE queue SET status='pending',error='' WHERE status IN ('done','error')")
    return {'ok':True}
@app.post('/api/documents/{id}/activate')
def activate_document(id:str):
    with db() as c:
        r=c.execute('SELECT kind FROM documents WHERE id=?',(id,)).fetchone()
        if not r:raise HTTPException(404,'Document not found')
        c.execute('UPDATE documents SET active=0 WHERE kind=?',(r['kind'],));c.execute('UPDATE documents SET active=1 WHERE id=?',(id,))
        c.execute("UPDATE queue SET status='pending',error='' WHERE status IN ('done','error')")
    return {'ok':True}
@app.get('/api/documents/{id}/original')
def original_download(id:str):
    with db() as c:r=c.execute('SELECT * FROM documents WHERE id=?',(id,)).fetchone()
    if not r:raise HTTPException(404,'Document not found')
    payload=unseal(r['payload'])
    # RFC 5987 filename encoding prevents response-header injection.
    from urllib.parse import quote
    return Response(base64.b64decode(payload['original']),media_type='application/octet-stream',headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(r['name'],safe='')})

@app.post('/api/jobs')
def import_job(p:JobImport):
    if p.workplace not in ('unknown','remote','hybrid','onsite'):raise ValueError('Unknown workplace')
    known={b['id'] for b in sources.BOARDS}|{'manual'}
    if p.source not in known:raise ValueError('Unknown source')
    value=p.model_dump(exclude={'save_to_saved','notes'});source=value.pop('source');j=sources.job(source,**value)
    if j is None:raise ValueError('A valid HTTPS job URL is required')
    if p.save_to_saved:
        status=store.save_imported_job(source,j,p.notes)
        return {'job':j,'savedTo':'applications' if status in ('applied','interviewing','rejected','offer','withdrawn') else 'saved'}
    upsert_jobs(source,[j]);return {'job':j,'savedTo':None}
@app.put('/api/jobs/{job_id}')
def update_job(job_id:str,p:ImportedJob):
    current=get_job(job_id)
    if not current:raise HTTPException(404,'Job not found')
    if not sources.url_ok(p.url):raise ValueError('A valid HTTPS job URL is required')
    if p.workplace not in ('unknown','remote','hybrid','onsite'):raise ValueError('Unknown workplace')
    updated={**current,**p.model_dump(),'id':job_id,'source':current['source'],'verified':True}
    upsert_jobs(current['source'],[updated]);return {'ok':True}
@app.put('/api/applications/{job_id}')
def update_application(job_id:str,p:ApplicationUpdate):
    if not get_job(job_id):raise HTTPException(404,'Job not found')
    if p.status not in ('new','saved','applied','interviewing','rejected','offer','withdrawn','hidden'):raise ValueError('Unknown status')
    now=time.time();days=get_setting('search',DEFAULT_SEARCH)['followup_days']
    with db() as c:
        old=c.execute('SELECT * FROM applications WHERE job_id=?',(job_id,)).fetchone()
        applied=p.applied if p.applied is not None else (old['applied'] if old else None)
        if applied and (applied<0 or applied>now+86400):raise ValueError('Applied date is invalid')
        if p.status in ('applied','interviewing','offer','rejected') and not applied and (not old or old['status'] not in ('applied','interviewing','offer','rejected')):applied=now
        due=p.followup if p.followup is not None else (None if old and old['applied'] and 'followup' in p.model_fields_set else old['followup'] if old and old['followup'] else applied+days*86400 if applied else None)
        c.execute('INSERT INTO applications VALUES(?,?,?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET status=excluded.status,notes=excluded.notes,applied=excluded.applied,followup=excluded.followup,updated=excluded.updated',(job_id,p.status,seal(p.notes),applied,due,now))
    return {'ok':True,'applied':applied,'followup':due}

@app.post('/api/jobs/{job_id}/prepare')
def prepare_job(job_id:str):return {'drafts':prepare(job_id)}
@app.post('/api/jobs/{job_id}/followup')
def followup_job(job_id:str):return prepare_followup(job_id)
@app.get('/api/jobs/{job_id}/drafts')
def job_drafts(job_id:str):
    with db() as c:rows=c.execute('SELECT * FROM drafts WHERE job_id=? ORDER BY created DESC',(job_id,)).fetchall()
    return {'drafts':[{'id':r['id'],'kind':r['kind'],'created':r['created'],'approved':bool(r['approved']),**unseal(r['payload'])} for r in rows]}
@app.put('/api/drafts/{id}')
def edit_draft(id:str,p:DraftUpdate):
    with db() as c:
        r=c.execute('SELECT payload FROM drafts WHERE id=?',(id,)).fetchone()
        if not r:raise HTTPException(404,'Draft not found')
        payload=unseal(r['payload']);payload.update(p.model_dump());c.execute('UPDATE drafts SET payload=?,approved=? WHERE id=?',(seal(payload),int(p.reviewed),id))
    return {'ok':True}
@app.get('/api/drafts/{id}/download')
def download_draft(id:str,format:str='docx'):
    with db() as c:r=c.execute('SELECT * FROM drafts WHERE id=?',(id,)).fetchone()
    if not r:raise HTTPException(404,'Draft not found')
    text=unseal(r['payload'])['text']
    if format=='docx':data=docx_bytes(text);mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    elif format=='pdf':data=pdf_bytes(text);mime='application/pdf'
    elif format=='txt':data=text.encode();mime='text/plain; charset=utf-8'
    else:raise ValueError('Choose docx, pdf, or txt')
    j=get_job(r['job_id']);name='-'.join((j or {}).get('company','job').split())[:50]
    import re
    name=re.sub(r'[^A-Za-z0-9_-]','',name) or 'job'
    return Response(data,media_type=mime,headers={'Content-Disposition':f'attachment; filename="{name}-{r["kind"]}.{format}"'})

@app.post('/api/migrate')
async def migrate(file:UploadFile=File(...)):
    raw=await file.read(12*1024*1024+1)
    if len(raw)>12*1024*1024:raise ValueError('Migration file exceeds 12 MB')
    try:data=json.loads(raw)
    except ValueError:raise ValueError('Upload the JSON exported from Job Radar')
    if not isinstance(data,dict) or not isinstance(data.get('jobs'),list) or len(data['jobs'])>5000:raise ValueError('Invalid migration file')
    groups={};identity_map={}
    for old in data['jobs']:
        if not isinstance(old,dict):continue
        j=sources.job(str(old.get('source','manual')),old.get('title'),old.get('company'),old.get('location'),old.get('url'),old.get('description'),salary=str(old.get('salary','')),type=str(old.get('type','')),date=str(old.get('date','')),workplace=old.get('workplace','remote'))
        if j:
            groups.setdefault(j['source'],[]).append(j)
            import re
            identity_map[':'.join(re.sub('[^a-z0-9]','',str(old.get(k,'')).lower()) for k in ['company','title','location'])]=j['id']
    for source,jobs in groups.items():upsert_jobs(source,jobs)
    restored=0
    for a in data.get('applications',[]):
        key=identity_map.get(a.get('id',''))
        if key and a.get('status') in ('new','saved','applied','interviewing','rejected','hidden'):
            applied=a.get('applied') if isinstance(a.get('applied'),(float,int)) and 0<a['applied']<=time.time() else None
            with db() as c:c.execute('INSERT OR IGNORE INTO applications VALUES(?,?,?,?,?,?)',(key,a['status'],seal(str(a.get('notes',''))[:20000]),applied,None,time.time()))
            restored+=1
    return {'imported':sum(map(len,groups.values())),'applications':restored}

@app.post('/api/jobs/{job_id}/details')
async def load_details(job_id:str):
    import httpx
    j=get_job(job_id)
    if not j:raise HTTPException(404,'Job not found')
    if j['source']!='dice' or not j.get('providerGuid'):raise ValueError('Paste the full description using Edit job for this source.')
    async with httpx.AsyncClient(timeout=25,follow_redirects=True) as client:
        response=await client.post('https://mcp.dice.com/mcp',json={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'get_job_details','arguments':{'job_id':j['providerGuid']}}},headers={'Accept':'application/json, text/event-stream'})
        payload=sources.jsonrpc(response)
    values=[payload.get('structuredContent')]
    for block in payload.get('content',[]):
        if block.get('type')=='text':
            try:values.append(json.loads(block['text']))
            except ValueError:pass
    def description(obj):
        if not isinstance(obj,dict):return ''
        for key in ['description','jobDescription','job_description','fullDescription']:
            if isinstance(obj.get(key),str):return sources.clean(obj[key])
        for key in ['data','job','result']:
            if key in obj:
                found=description(obj[key])
                if found:return found
        return ''
    text=next((s for x in values if len(s:=description(x))>=80),'')
    if not text:raise ValueError('The full description was not available. Paste it from the original listing.')
    j['description']=text[:60000];j['verified']=True
    upsert_jobs(j['source'],[j]);return {'job':j}



@app.get('/api/jobs/{job_id}/apply-options')
async def apply_options(job_id:str):
    job = get_job(job_id)
    if not job: raise HTTPException(404, 'Job not found')
    return await application_options(job)


class JobFetchRequest(BaseModel):
    url:str=Field(min_length=10,max_length=2000)

import_fetch_limit=asyncio.Semaphore(2)

@app.post('/api/import/fetch')
async def fetch_import(p:JobFetchRequest):
    async with import_fetch_limit:
        return await asyncio.to_thread(fetch_details,p.url)

app.mount('/',StaticFiles(directory=Path(__file__).parent/'static',html=True),name='ui')
