"""Tenant-boundary tests use real signed Access JWTs and fictional identities."""
import asyncio
import io
import sqlite3
import tarfile
import time
from types import SimpleNamespace
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from radar import store,security,sources
from radar.app import app,maintain_workspaces,running_tasks
from test_app import JOB,RESUME

OWNER='owner@example.test'
FRIEND='friend@example.test'
OTHER='other@example.test'

@pytest.fixture
def tenants(monkeypatch,tmp_path):
    monkeypatch.setattr(store,'DATA',tmp_path)
    monkeypatch.setattr(store,'DB_PATH',tmp_path/'radar.sqlite')
    monkeypatch.setattr(store,'REGISTRY',tmp_path/'workspaces.sqlite')
    monkeypatch.setattr(store,'OWNER_EMAIL',None)
    monkeypatch.setenv('RADAR_AUTH_MODE','cloudflare')
    monkeypatch.setenv('RADAR_OWNER_EMAIL',OWNER)
    monkeypatch.setattr(security,'MODE','cloudflare')
    monkeypatch.setattr(security,'TEAM','beta.cloudflareaccess.com')
    monkeypatch.setattr(security,'AUD','beta-audience')
    monkeypatch.setattr(security,'ALLOWED',{OWNER,FRIEND,OTHER})
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    monkeypatch.setattr(security,'CLIENT',SimpleNamespace(get_signing_key_from_jwt=lambda token:SimpleNamespace(key=key.public_key())))
    # Simulate an existing 2.6 installation before the new identity registry exists.
    token=store.CURRENT_WORKSPACE.set('owner')
    try:
        store.init();store.put_setting('profile',{**store.DEFAULT_PROFILE,'name':'Existing Owner','email':OWNER})
        store.put_setting('search',{**store.DEFAULT_SEARCH,'keywords':'Legacy IT search'})
        with store.db() as c:c.execute('INSERT INTO documents VALUES(?,?,?,?,?,1)',('legacy-document','resume','legacy.txt',store.seal({'text':RESUME,'original':'','id':'legacy-document'}),time.time()))
    finally:store.CURRENT_WORKSPACE.reset(token)
    def headers(email=OWNER,**claims):
        now=int(time.time())
        value={'iss':'https://beta.cloudflareaccess.com','aud':'beta-audience','email':email,'sub':'subject-'+str(email),'iat':now,'exp':now+300,**claims}
        return {'Cf-Access-Jwt-Assertion':jwt.encode(value,key,algorithm='RS256'),'Origin':'http://testserver'}
    with TestClient(app) as client:yield client,headers,tmp_path


def test_friend_first_cannot_claim_legacy_workspace(tenants):
    c,h,path=tenants
    with store.workspace_context(OWNER):
        legacy=sources.job('manual','Legacy Role','Legacy Demo Employer','Remote','https://example.test/legacy','An existing imported legacy job description.')
        store.upsert_jobs('manual',[legacy])
        with store.db() as db:
            db.execute('INSERT INTO applications VALUES(?,?,?,?,?,?)',(legacy['id'],'applied',store.seal('Legacy note'),time.time(),None,time.time()))
            db.execute('INSERT INTO drafts VALUES(?,?,?,?,?,0)',('legacy-draft',legacy['id'],'resume',store.seal({'text':'Legacy draft preserved'}),time.time()))
    friend=c.get('/api/workspace',headers=h(FRIEND)).json()
    assert friend['identity']['email']==FRIEND
    assert friend['profile']['name']=='' and friend['profile']['email']==FRIEND
    assert friend['documents']==friend['applications']==friend['jobs']==friend['drafts']==[]
    assert friend['search']['keywords']=='IT support'
    assert c.get('/api/profile/answers',headers=h(FRIEND)).status_code==400
    owner=c.get('/api/workspace',headers=h()).json()
    assert owner['profile']['name']=='Existing Owner'
    assert owner['documents'][0]['id']=='legacy-document'
    assert owner['search']['keywords']=='Legacy IT search'
    assert owner['applications'][0]['notes']=='Legacy note'
    assert owner['drafts'][0]['id']=='legacy-draft'
    assert (path/'radar.sqlite').exists()
    assert len(list((path/'workspaces').glob('*.sqlite')))==1
    assert FRIEND.encode() not in store.REGISTRY.read_bytes()
    assert c.get('/api/documents/legacy-document',headers=h(FRIEND)).status_code==404
    # Case normalization must not create a second account.
    assert c.get('/api/workspace',headers=h(FRIEND.upper())).json()['identity']['email']==FRIEND
    assert len(list((path/'workspaces').glob('*.sqlite')))==1


def test_all_personal_routes_are_isolated_even_with_known_ids(tenants):
    c,h,_=tenants
    owner,friend=h(),h(FRIEND)
    doc=c.post('/api/documents',headers=owner,data={'kind':'resume'},files={'file':('owner-resume.txt',RESUME.encode(),'text/plain')}).json()['id']
    job=c.post('/api/jobs',headers=owner,json=JOB).json()['job']['id']
    c.put('/api/applications/'+job,headers=owner,json={'status':'applied','notes':'Owner private note'})
    draft=c.post('/api/jobs/'+job+'/prepare',headers=owner).json()['drafts'][0]['id']
    for suffix in ['', '/original']:
        assert c.get('/api/documents/'+doc+suffix,headers=friend).status_code==404
    assert c.put('/api/documents/'+doc,headers=friend,json={'text':'Unauthorized text modification should not be allowed.'}).status_code==404
    assert c.post('/api/documents/'+doc+'/activate',headers=friend).status_code==404
    assert c.put('/api/jobs/'+job,headers=friend,json=JOB).status_code==404
    assert c.put('/api/applications/'+job,headers=friend,json={'status':'applied'}).status_code==404
    assert c.get('/api/jobs/'+job+'/apply-options',headers=friend).status_code==404
    assert c.post('/api/jobs/'+job+'/details',headers=friend).status_code==404
    assert c.post('/api/jobs/'+job+'/prepare',headers=friend).status_code==400
    assert c.post('/api/jobs/'+job+'/followup',headers=friend).status_code==400
    assert c.get('/api/jobs/'+job+'/drafts',headers=friend).json()['drafts']==[]
    for fmt in ['txt','pdf','docx']:
        assert c.get('/api/drafts/'+draft+'/download?format='+fmt,headers=friend).status_code==404
    assert c.put('/api/drafts/'+draft,headers=friend,json={'text':'Attempted cross-workspace edit is rejected.'}).status_code==404
    # Same public job ID can have independent statuses in separate databases.
    assert c.post('/api/jobs',headers=friend,json=JOB).json()['job']['id']==job
    c.put('/api/applications/'+job,headers=friend,json={'status':'saved','notes':'Friend private note'})
    assert c.get('/api/jobs/'+job+'/drafts',headers=friend).json()['drafts']==[]
    a=c.get('/api/workspace',headers=owner).json()['applications'][0]
    b=c.get('/api/workspace',headers=friend).json()['applications'][0]
    assert (a['status'],a['notes'])==('applied','Owner private note')
    assert (b['status'],b['notes'])==('saved','Friend private note')
    # Contact email is editable for documents; it never changes authenticated ownership.
    c.put('/api/profile',headers=friend,json={'name':'Friend Demo','email':OWNER,'home_address':'Albany, NY'})
    assert c.get('/api/workspace',headers=friend).json()['identity']['email']==FRIEND
    assert c.get('/api/workspace',headers=owner).json()['profile']['name']=='Existing Owner'


def test_allowlist_and_verified_claims_are_required(tenants):
    c,h,path=tenants
    for headers in [h('uninvited@example.test'),h(None),h(123),h('bad email'),h(FRIEND,aud='other-app'),h(FRIEND,iss='https://wrong.cloudflareaccess.com'),h(FRIEND,exp=int(time.time())-5),{'Cf-Access-Authenticated-User-Email':OWNER}]:
        assert c.get('/api/workspace',headers=headers).status_code==401
    spoof={**h(FRIEND),'Cf-Access-Authenticated-User-Email':OWNER,'X-Workspace-Id':'owner'}
    result=c.get('/api/workspace?email='+OWNER,headers=spoof).json()
    assert result['identity']['email']==FRIEND and result['documents']==[]
    assert c.get('/api/workspace',headers={**h(FRIEND),'Cf-Access-Jwt-Assertion':'not-a-jwt'}).status_code==401
    assert c.put('/api/profile',headers={**h(FRIEND),'Origin':'https://other.example.test'},json={'name':'Friend'}).status_code==403
    security.ALLOWED.remove(FRIEND)
    assert c.get('/api/workspace',headers=h(FRIEND)).status_code==401
    assert FRIEND not in store.workspace_emails(security.ALLOWED)
    with pytest.raises(RuntimeError):
        with store.db():pass


def test_owner_binding_survives_restart_and_allowlist_order(tenants):
    c,h,_=tenants
    store.configure_workspaces('cloudflare',{OTHER,FRIEND,OWNER})
    assert store.OWNER_EMAIL==OWNER
    with pytest.raises(RuntimeError):store.configure_workspaces('cloudflare',{OWNER,FRIEND},FRIEND)
    assert c.get('/api/workspace',headers=h()).json()['documents'][0]['id']=='legacy-document'


def test_ambiguous_owner_fails_closed_before_any_login(monkeypatch,tmp_path):
    monkeypatch.setattr(store,'REGISTRY',tmp_path/'workspaces.sqlite')
    monkeypatch.setattr(store,'OWNER_EMAIL',None)
    with pytest.raises(RuntimeError,match='RADAR_OWNER_EMAIL'):
        store.configure_workspaces('cloudflare',{OWNER,FRIEND})
    assert store.OWNER_EMAIL is None
    store.configure_workspaces('cloudflare',{OWNER})
    assert store.OWNER_EMAIL==OWNER
    store.configure_workspaces('cloudflare',{OWNER,FRIEND})
    assert store.OWNER_EMAIL==OWNER


def test_all_workspace_backup_includes_legacy_registry_and_friends(tenants):
    from radar.backup import backup_all
    c,h,path=tenants
    c.get('/api/workspace',headers=h(FRIEND))
    c.post('/api/jobs',headers=h(FRIEND),json=JOB)
    output=backup_all(path/'backup.tar.gz',path)
    with tarfile.open(output) as archive:
        names=archive.getnames()
        assert 'radar.sqlite' in names and 'workspaces.sqlite' in names
        friend_db=next(n for n in names if n.startswith('workspaces/'))
        assert FRIEND not in friend_db
        restored=path/'restored.sqlite';restored.write_bytes(archive.extractfile(friend_db).read())
        with sqlite3.connect(restored) as db:assert db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]==1
    assert output.stat().st_mode&0o777==0o600


def test_concurrent_requests_keep_identity_in_sync_and_async_routes(tenants):
    import httpx
    c,h,_=tenants
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
            async def user(email):
                for i in range(3):
                    response=await client.put('/api/profile',headers=h(email),json={'name':email,'home_address':email.split('@')[0]+' Demo ZIP'})
                    assert response.status_code==200
                    result=(await client.get('/api/workspace',headers=h(email))).json()
                    assert result['identity']['email']==email and result['profile']['name']==email
            await asyncio.gather(user(OWNER),user(FRIEND),user(OTHER))
    asyncio.run(run())


def test_public_feeds_shared_but_imports_and_search_settings_private(tenants,monkeypatch):
    c,h,_=tenants
    board={'id':'demo-public','name':'Demo public board','mode':'feed','url':'https://example.test'}
    monkeypatch.setattr(sources,'BOARDS',[board]);calls=[]
    async def fetch(*args):
        calls.append(1)
        return [sources.job('demo-public','IT Support','Public Demo Employer','Remote','https://example.test/public','Public demonstration job description.')],True
    monkeypatch.setattr(sources,'fetch_board',fetch)
    async def run():
        for email in [OWNER,FRIEND]:
            store.ensure_workspace(email)
            with store.workspace_context(email):await sources.scan_sources()
    asyncio.run(run())
    assert len(calls)==1
    for email in [OWNER,FRIEND]:assert len(c.get('/api/workspace',headers=h(email)).json()['jobs'])==1
    public_job=c.get('/api/workspace',headers=h()).json()['jobs'][0]['id']
    changed=c.put('/api/jobs/'+public_job,headers=h(),json={**JOB,'company':'Owner Private Edit'})
    assert changed.status_code==200
    assert c.get('/api/workspace',headers=h(FRIEND)).json()['jobs'][0]['company']=='Public Demo Employer'
    # A manual import in one account never enters the public cache.
    c.post('/api/jobs',headers=h(),json=JOB)
    assert len(c.get('/api/workspace',headers=h(FRIEND)).json()['jobs'])==1
    c.put('/api/search',headers=h(FRIEND),json={'keywords':'Network engineer','location':'Buffalo, NY','workplace':'hybrid','auto_prepare':False,'followup_days':3})
    assert c.get('/api/workspace',headers=h()).json()['search']['keywords']=='Legacy IT search'
    assert c.get('/api/workspace',headers=h(FRIEND)).json()['search']['keywords']=='Network engineer'


def test_background_tasks_and_scan_flags_keep_workspace_context(tenants,monkeypatch):
    import httpx
    c,h,_=tenants
    seen=[]
    async def scan():
        ident=store.current_workspace();sources.SCANNING.add(ident)
        await asyncio.sleep(0.02)
        store.put_setting('background_marker',ident)
        seen.append(ident);sources.SCANNING.discard(ident)
    monkeypatch.setattr(sources,'scan_sources',scan)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
            await asyncio.gather(*(client.post('/api/scan',headers=h(email)) for email in [OWNER,FRIEND]))
            await asyncio.gather(*list(running_tasks))
        assert len(set(seen))==2
        for email in [OWNER,FRIEND]:
            with store.workspace_context(email):
                assert store.get_setting('background_marker')==store.current_workspace()
                assert not sources.scan_running()
        seen.clear()
        await maintain_workspaces()
        assert len(set(seen))==2
    asyncio.run(run())


def test_distinct_search_queries_never_reuse_other_users_results(tenants,monkeypatch):
    c,h,_=tenants
    board={'id':'demo-index','name':'Demo index','mode':'indexed','url':'https://example.test'}
    monkeypatch.setattr(sources,'BOARDS',[board]);calls=[]
    async def fetch(client,board,search):
        calls.append(search['keywords'])
        return [sources.job(board['id'],search['keywords'],'Public Search Demo','Remote','https://example.test/'+str(len(calls)),'Public demonstration job description.')],False
    monkeypatch.setattr(sources,'fetch_board',fetch)
    async def run():
        for email in [OWNER,FRIEND]:
            store.ensure_workspace(email)
            with store.workspace_context(email):await sources.scan_sources()
    asyncio.run(run())
    assert calls==['Legacy IT search','IT support']
    assert c.get('/api/workspace',headers=h(FRIEND)).json()['jobs'][0]['title']=='IT support'
    assert c.get('/api/workspace',headers=h()).json()['jobs'][0]['title']=='Legacy IT search'


def test_private_workspaces_and_backup_archives_cannot_be_published():
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('privacy_guard',Path(__file__).parents[1]/'deploy/check_public_tree.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    for name in ['data/radar.sqlite','workspaces/abc.sqlite','workspaces.sqlite-wal','backups/all.tar.gz','.env','radar.sqlite-shm']:
        assert module.forbidden(name)
    assert not module.forbidden('.env.example')
    assert not module.forbidden('tests/test_workspaces.py')
