import asyncio,json
from pathlib import Path
import httpx
from radar import sources,apply
from radar.catalog import ROOT

def test_all_100_image_entries_present_once():
 rows=[line.split('|') for line in (ROOT/'source_catalog.txt').read_text().splitlines()]
 assert len(rows)==100 and len({r[0]for r in rows})==100
 ids=[b['id']for b in sources.BOARDS]
 assert len(ids)==len(set(ids))
 assert {r[0]for r in rows}<=set(ids)
 assert set(ids)==set(apply.AUDIT)
 assert len(json.loads((ROOT/'source_review.json').read_text()))==100
 assert all(b['url'].startswith('https://')for b in sources.BOARDS)
 assert {b['id']for b in sources.BOARDS}>={'teal','jobleads','jobilize','ziprecruiter','obra','bandana'}

def test_verified_ats_config_only_successful_public_feeds():
 records=json.loads((ROOT/'verified_boards.json').read_text());checks=json.loads((ROOT/'feed_review.json').read_text())
 for ident,settings in records.items():
  assert any(c['id']==ident and c.get('status')==200 and c['board']==settings['board'] and c.get('count') is not None for c in checks)
  b=next(b for b in sources.BOARDS if b['id']==ident)
  assert b['mode']==settings['mode']
  assert apply.source_audit(ident)['mode']=='conditional'

def test_public_feed_mapping_and_attribution():
 async def run():
  def handler(request):
   if request.url.host=='remoteok.com':return httpx.Response(200,json=[{'legal':'Terms'},{'position':'Support','company':'Example','url':'https://remoteok.com/remote-jobs/1','apply_url':'https://employer.example/apply','description':'Help users'}])
   return httpx.Response(200,text='<rss><channel><item><title>Example: Systems Administrator</title><link>https://weworkremotely.com/remote-jobs/1</link><description>Manage systems</description></item></channel></rss>')
  async with httpx.AsyncClient(transport=httpx.MockTransport(handler))as c:
   remote=await sources.public_jobs(c,{'id':'remoteok','mode':'remoteok'})
   wwr=await sources.public_jobs(c,{'id':'weworkremotely','mode':'wwr'})
  assert remote[0]['company']=='Example' and remote[0]['url'].startswith('https://remoteok.com/')
  assert wwr[0]['title']=='Systems Administrator' and wwr[0]['company']=='Example'
  assert apply.candidate(remote[0])is None and apply.candidate(wwr[0])is None
 asyncio.run(run())

def test_ashby_collectors_keep_company_source_identity():
 async def run():
  def handler(request):return httpx.Response(200,json={'jobs':[{'title':'Support','jobUrl':'https://jobs.ashbyhq.com/zapier/7458d4e9-da2e-47bd-98cb-adfda43d42b2','applyUrl':'https://jobs.ashbyhq.com/zapier/7458d4e9-da2e-47bd-98cb-adfda43d42b2/application','workplaceType':'Remote'}]})
  async with httpx.AsyncClient(transport=httpx.MockTransport(handler))as c:
   jobs=await sources.ashby_jobs(c,{'id':'zapier','name':'Zapier Jobs','board':'zapier'})
  assert jobs[0]['source']=='zapier' and jobs[0]['company']=='Zapier Jobs'
  assert jobs[0]['id'].startswith('zapier:')
 asyncio.run(run())

def test_greenhouse_custom_board_slug_not_source_id():
 async def run():
  def handler(request):
   assert request.url.path=='/v1/boards/digitalocean98/jobs'
   return httpx.Response(200,json={'jobs':[{'id':1,'title':'Support','absolute_url':'https://job-boards.greenhouse.io/digitalocean98/jobs/1','content':'Description','location':{'name':'Remote'}}]})
  async with httpx.AsyncClient(transport=httpx.MockTransport(handler))as c:
   rows,_=await sources.fetch_board(c,{'id':'digitalocean','name':'DigitalOcean','mode':'greenhouse','board':'digitalocean98'},{})
  assert rows[0]['source']=='digitalocean'
  assert '/digitalocean98/' in rows[0]['applicationUrl']
 asyncio.run(run())

def test_lever_feed_read_only_and_preserves_apply_link():
 async def run():
  def handler(request):
   assert request.method=='GET' and request.url.host=='api.eu.lever.co'
   return httpx.Response(200,json=[{'text':'Support','hostedUrl':'https://jobs.eu.lever.co/example/1','applyUrl':'https://jobs.eu.lever.co/example/1/apply','categories':{'location':'Europe'},'workplaceType':'remote','descriptionPlain':'Help','lists':[{'text':'Requirements','content':'Linux'}]}])
  async with httpx.AsyncClient(transport=httpx.MockTransport(handler))as c:
   rows=await sources.public_jobs(c,{'id':'fixture','name':'Example','mode':'lever','board':'example','region':'eu'})
  assert rows[0]['workplace']=='remote' and 'Linux' in rows[0]['description']
  assert rows[0]['applicationUrl'].endswith('/apply')
 asyncio.run(run())
