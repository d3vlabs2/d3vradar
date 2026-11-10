from fastapi.testclient import TestClient
from radar.app import app
from radar.store import db
from test_app import HEADERS,JOB

def test_home_origin_is_encrypted_and_office_can_be_saved():
 with TestClient(app,headers=HEADERS)as c:
  p=c.get('/api/workspace').json()['profile']
  p['home_address']='123 Private Example Street, Albany, NY'
  assert c.put('/api/profile',json=p).status_code==200
  assert c.get('/api/workspace').json()['profile']['home_address']==p['home_address']
  with db()as conn:assert p['home_address'] not in str(conn.execute("SELECT payload FROM settings WHERE id='profile'").fetchone()['payload'])
  job=c.post('/api/jobs',json={**JOB,'officeAddress':'456 Business Road, Buffalo, NY'}).json()['job']
  assert job['officeAddress']=='456 Business Road, Buffalo, NY'
  policy=c.get('/').headers['content-security-policy']
  assert 'https://www.google.com/maps/embed/'in policy and "frame-ancestors 'none'"in policy

def test_optional_maps_key_is_authenticated(monkeypatch):
 monkeypatch.setenv('GOOGLE_MAPS_EMBED_API_KEY','restricted-browser-key')
 with TestClient(app,headers=HEADERS)as c:
  assert c.get('/api/workspace').json()['mapsEmbedKey']=='restricted-browser-key'
  assert c.get('/api/workspace',headers={'Authorization':''}).status_code==401
