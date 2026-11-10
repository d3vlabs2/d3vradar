import asyncio
import httpx
import pytest
from radar import apply, sources
from radar.app import app
from radar.store import upsert_jobs
from fastapi.testclient import TestClient
from test_app import HEADERS

@pytest.mark.parametrize('url,provider',[
 ('https://job-boards.greenhouse.io/cloudflare/jobs/123?gh_src=abc','Greenhouse'),
 ('https://boards.greenhouse.io/embed/job_app?for=gitlab&token=123','Greenhouse'),
 ('https://jobs.ashbyhq.com/Example/7458d4e9-da2e-47bd-98cb-adfda43d42b2/application','Ashby'),
])
def test_known_application_routes(url,provider):
 result=apply.candidate({'url':url,'source':'manual'})
 assert result['provider']==provider
 assert 'application' in result['embedUrl'] or 'job_app' in result['embedUrl']

@pytest.mark.parametrize('url',[
 'http://boards.greenhouse.io/x/jobs/123','https://job-boards.greenhouse.io.evil.test/x/jobs/123',
 'https://job-boards.greenhouse.io@127.0.0.1/x/jobs/123','https://job-boards.greenhouse.io:444/x/jobs/123',
 'https://jobs.ashbyhq.com/x/../../admin','https://localhost/jobs/1','https://boards.greenhouse.io/embed/job_app?for=../../x&token=123',
])
def test_rejects_unrecognized_urls(url):
 assert apply.candidate({'url':url,'source':'manual'}) is None

@pytest.mark.parametrize('source',['himalayas','remotive'])
def test_attribution_routes_remain_external(source):
 assert apply.candidate({'source':source,'url':'https://boards.greenhouse.io/x/jobs/123'}) is None

def test_all_sources_have_audit():
 assert {b['id'] for b in sources.BOARDS} == set(apply.AUDIT)
 assert all(apply.source_audit(b['id'])['documentation'].startswith('https://') for b in sources.BOARDS)

@pytest.mark.parametrize('headers,blocked',[
 ({'x-frame-options':'DENY'},True),({'x-frame-options':'SAMEORIGIN'},True),
 ({'content-security-policy':"frame-ancestors 'none'"},True),
 ({'content-security-policy':"frame-ancestors https://employer.example"},True),
 ({'content-security-policy':'frame-ancestors '+apply.ORIGIN},False),
 ({'content-security-policy':'frame-ancestors *'},False),({},False),
])
def test_frame_restrictions(headers,blocked):
 assert bool(apply.frame_block(headers)) == blocked

@pytest.mark.parametrize('status,headers,mode',[
 (200,{'content-type':'text/html'},'embed'),
 (200,{'content-type':'text/html','x-frame-options':'DENY'},'external'),
 (302,{'location':'https://127.0.0.1/'},'external'),
 (403,{},'external'),(200,{'content-type':'application/json'},'external'),
])
def test_probe_does_not_follow_redirects_or_submit(status,headers,mode):
 apply.CACHE.clear()
 seen=[]
 def handler(request):
  seen.append(request)
  return httpx.Response(status,headers=headers,text='<html>Employer form</html>')
 async def run():
  async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
   return await apply.application_options({'id':'fixture','source':'greenhouse','url':'https://boards.greenhouse.io/x/jobs/123'},c)
 result=asyncio.run(run())
 assert result['mode']==mode
 assert len(seen)==1 and seen[0].method=='GET'
 assert not seen[0].content
 assert 'authorization' not in seen[0].headers
 assert ('embedUrl' in result) == (mode=='embed')

def test_options_endpoint_requires_auth_and_never_marks_applied():
 with TestClient(app,headers=HEADERS) as c:
  upsert_jobs('manual',[{'id':'apply:test','source':'manual','url':'https://example.test/job/1','title':'Support','description':'Description','company':'Example','location':'Remote'}])
  assert c.get('/api/jobs/apply:test/apply-options',headers={'Authorization':''}).status_code==401
  assert c.get('/api/jobs/missing/apply-options').status_code==404
  assert c.get('/api/jobs/apply:test/apply-options').json()['mode']=='external'
  assert not any(a['job_id']=='apply:test' for a in c.get('/api/workspace').json()['applications'])
  policy=c.get('/').headers['content-security-policy']
  assert "script-src 'self';" in policy
  assert "frame-ancestors 'none'" in policy
  assert 'https://job-boards.greenhouse.io https://jobs.ashbyhq.com;' in policy
