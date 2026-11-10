import time
from fastapi.testclient import TestClient
from radar.app import app
from radar import store
from test_app import HEADERS,JOB
from test_workspaces import tenants,OWNER,FRIEND


def test_import_bookmarks_job_with_notes_and_no_applied_date():
    with TestClient(app,headers=HEADERS) as c:
        url='https://example.test/one-dialog-import'
        result=c.post('/api/jobs',json={**JOB,'url':url,'notes':'Review this opportunity next week.'})
        assert result.status_code==200 and result.json()['savedTo']=='saved'
        ident=result.json()['job']['id'];workspace=c.get('/api/workspace').json()
        record=next(a for a in workspace['applications'] if a['job_id']==ident)
        assert record['status']=='saved' and record['applied'] is None and record['followup'] is None
        assert record['notes']=='Review this opportunity next week.'
        with store.db() as db:assert b'Review this opportunity' not in db.execute('SELECT notes FROM applications WHERE job_id=?',(ident,)).fetchone()['notes']


def test_reimport_keeps_application_status_dates_and_notes():
    with TestClient(app,headers=HEADERS) as c:
        payload={**JOB,'url':'https://example.test/already-applied'}
        ident=c.post('/api/jobs',json=payload).json()['job']['id']
        applied=time.time()-86400;followup=time.time()+86400
        c.put('/api/applications/'+ident,json={'status':'interviewing','notes':'Interview booked.','applied':applied,'followup':followup})
        result=c.post('/api/jobs',json={**payload,'notes':'Additional import note.'}).json()
        assert result['savedTo']=='applications'
        record=next(a for a in c.get('/api/workspace').json()['applications'] if a['job_id']==ident)
        assert record['status']=='interviewing' and record['applied']==applied and record['followup']==followup
        assert record['notes']=='Interview booked.\n\nAdditional import note.'


def test_import_save_is_atomic(monkeypatch):
    with TestClient(app,headers=HEADERS) as c:
        payload={**JOB,'url':'https://example.test/rollback-import'}
        def fail(value):raise ValueError('Synthetic note encryption failure')
        monkeypatch.setattr(store,'seal',fail)
        assert c.post('/api/jobs',json=payload).status_code==400
        assert not any(j['url']==payload['url'] for j in c.get('/api/workspace').json()['jobs'])


def test_imported_bookmarks_remain_private(tenants):
    c,h,_=tenants
    result=c.post('/api/jobs',headers=h(),json={**JOB,'notes':'Owner import note.'}).json()
    assert result['savedTo']=='saved'
    friend=c.get('/api/workspace',headers=h(FRIEND)).json()
    assert friend['jobs']==friend['applications']==[]
