"""Provider-supported application embeds; never submit or proxy applicant data."""
import re
import time
from urllib.parse import urlsplit, parse_qs, urlencode
import httpx
from .security import ORIGIN

CHECKED = '2026-11-09'
GH_DOC = 'https://support.greenhouse.io/hc/en-us/articles/200721644-Choose-a-careers-page-integration-option'
ASHBY_DOC = 'https://docs.ashbyhq.com/embedding-ashby-job-boards-in-an-external-careers-page'
AUDIT = {
 'remotive': ('external', 'Use the original Remotive listing and its application route.', 'https://remotive.com/remote-jobs/api'),
 'himalayas': ('external', 'Preserves the original Himalayas applicationLink; no ATS shortcut.', 'https://himalayas.app/docs/remote-jobs-api'),
 'canonical': ('conditional', 'Greenhouse form when the actual job link supports embedding.', GH_DOC),
 'cloudflare': ('conditional', 'Greenhouse form when the actual job link supports embedding.', GH_DOC),
 'gitlab': ('conditional', 'Greenhouse form when the actual job link supports embedding.', GH_DOC),
 'greenhouse': ('conditional', 'Public employer Greenhouse application embeds; employer restrictions still apply.', GH_DOC),
 'ashby': ('conditional', 'Application embed when enabled by the hiring company.', ASHBY_DOC),
 'dice': ('external', 'Search MCP does not grant application submission. No public seeker submission integration verified.', 'https://www.dice.com/career-advice/how-to-connect-the-dice-mcp-server-to-your-ai-assistant'),
 'ziprecruiter': ('external', 'Apply integration is an employer/ATS partner workflow, not a personal submission API.', 'https://www.ziprecruiter.com/partner/documentation/apply-webhook/'),
 'linkedin': ('external', 'Easy Apply runs on LinkedIn; partner integrations are not enabled for this private app.', 'https://www.linkedin.com/help/linkedin/answer/a512388'),
 'indeed': ('external', 'Indeed Apply requires an approved partner integration and agreement.', 'https://docs.indeed.com/indeed-apply/agencies-and-third-party-platforms'),
 'obra': ('unverified', 'No public candidate submission or embed integration verified. Use the provider application route.', 'https://obra.co/'),
 'bandana': ('unverified', 'Bandana Apply/Match is provider-managed. No public embed integration verified.', 'https://resources.bandana.com/bandana-job-match'),
 'glassdoor': ('unverified', 'No public candidate submission or embed integration verified. Apply on the provider or employer site.', 'https://www.glassdoor.com/blog/guide/how-to-apply-for-a-job/'),
 'teal': ('unverified', 'Job discovery and tracking do not provide a verified public submission integration.', 'https://help.tealhq.com/en/articles/13456939-using-teal-s-job-search'),
 'jobleads': ('external', 'JobLeads redirects to the original posting for applications.', 'https://support.jobleads.com/hc/en-us/articles/12298304413842-Can-I-apply-directly-from-JobLeads'),
 'jobilize': ('unverified', 'Employer application routes vary; no public submission or embed integration verified.', 'https://www.jobilize.com/'),
}
# Full photo catalog is covered explicitly. Unverified is not advertised as supported.
from .catalog import expand_boards
for _board in expand_boards([]):
    AUDIT.setdefault(_board['id'], ('unverified','No public candidate submission or employer-approved embed verified for this source. Known Greenhouse/Ashby job URLs are checked individually; otherwise apply externally.',_board['url']))
    if _board['mode'] in ('greenhouse','ashby'):
        AUDIT[_board['id']]=('conditional','Public employer ATS feed verified. In-Radar applications are checked against the actual job URL and employer framing policy.',GH_DOC if _board['mode']=='greenhouse' else ASHBY_DOC)
AUDIT['lever']=('external','Lever does not provide application iframes; submission API requires an employer Super Admin API key.','https://github.com/lever/postings-api')
AUDIT['weworkremotely']=('external','Preserves the original We Work Remotely listing and source attribution.','https://weworkremotely.com/remote-job-rss-feed')
AUDIT['remoteok']=('external','Preserves Remote OK listing links and attribution required by its API.','https://remoteok.com/api')

CACHE = {}

def source_audit(source):
    mode, reason, documentation = AUDIT.get(source, ('unverified','No supported application integration verified.',''))
    return {'mode':mode, 'reason':reason, 'documentation':documentation, 'reviewed':CHECKED}

def candidate(job):
    # Source attribution routes must remain unchanged even if their URLs point to an ATS.
    if job.get('source') in ('remotive','himalayas','weworkremotely','remoteok'): return None
    for raw in (job.get('applicationUrl'), job.get('url')):
        try:
            p = urlsplit(raw or '')
            if p.scheme != 'https' or p.username or p.password or p.port not in (None,443): continue
            query = parse_qs(p.query)
            if p.hostname in ('boards.greenhouse.io','job-boards.greenhouse.io'):
                m = re.fullmatch(r'/([A-Za-z0-9_-]+)/jobs/(\d+)/?',p.path)
                if m: board, ident = m.groups()
                elif p.path.rstrip('/') == '/embed/job_app':
                    board, ident = query.get('for',[''])[0],query.get('token',[''])[0]
                    if not re.fullmatch(r'[A-Za-z0-9_-]+',board) or not ident.isdigit(): continue
                else: continue
                params = {'for':board,'token':ident}
                if query.get('gh_src'): params['gh_src'] = query['gh_src'][0][:200]
                return {'provider':'Greenhouse','embedUrl':'https://job-boards.greenhouse.io/embed/job_app?'+urlencode(params)}
            if p.hostname == 'jobs.ashbyhq.com':
                m = re.fullmatch(r'/([A-Za-z0-9_-]+)/([a-fA-F0-9-]{36})(?:/application)?/?',p.path)
                if not m: continue
                board, ident = m.groups()
                params = {'embed':'js','displayMode':'application-form-only'}
                if query.get('utm_source'): params['utm_source']=query['utm_source'][0][:200]
                return {'provider':'Ashby','embedUrl':f'https://jobs.ashbyhq.com/{board}/{ident}/application?'+urlencode(params)}
        except ValueError: continue
    return None

def frame_block(headers):
    xfo = headers.get('x-frame-options','').strip().upper()
    if xfo: return 'Provider sends an embedding restriction ('+xfo[:40]+').'  # Conservative: do not override XFO.
    for policy in headers.get('content-security-policy','').split(','):
        for directive in policy.split(';'):
            bits = directive.strip().split()
            if not bits or bits[0].lower() != 'frame-ancestors': continue
            allowed = bits[1:]
            if "'none'" in allowed: return 'Provider blocks embedded applications.'
            if not any(value in ('*','https:',ORIGIN) for value in allowed):
                return 'Employer embedding policy does not permit this Radar origin.'
    return None

async def application_options(job, client=None):
    result = {'mode':'external', 'reason':source_audit(job.get('source'))['reason'], 'externalUrl':job.get('applicationUrl') or job['url'], 'audit':source_audit(job.get('source'))}
    if job.get('source') in ('remotive','himalayas','weworkremotely','remoteok'): result['externalUrl']=job['url']
    spec = candidate(job)
    if not spec: return result
    key = spec['embedUrl']
    cached = CACHE.get(key)
    if cached and cached[0] > time.monotonic(): return {**result, **cached[1]}
    async def check(c):
        # Only fixed, validated ATS hosts. No redirects, no cookies or profile data.
        async with c.stream('GET', key, follow_redirects=False, headers={'Accept':'text/html'}) as response:
            if response.status_code != 200: return {'reason':'Provider form could not be verified (HTTP '+str(response.status_code)+'). Use the external application.'}
            if 'text/html' not in response.headers.get('content-type',''): return {'reason':'Provider did not return an application page.'}
            blocked=frame_block(response.headers)
            if blocked: return {'reason':blocked+' Use the external application.'}
            return {**spec,'mode':'embed','reason':'Provider supports this embed route. Complete and submit the employer form below. Login, cookies, or employer settings may still require opening it externally.'}
    try:
        if client is not None: checked=await check(client)
        else:
            async with httpx.AsyncClient(timeout=10) as c: checked=await check(c)
    except httpx.HTTPError: checked={'reason':'Provider form check is unavailable. Use the external application.'}
    if len(CACHE)>512: CACHE.clear()
    CACHE[key]=(time.monotonic()+300,checked)
    return {**result, **checked}
