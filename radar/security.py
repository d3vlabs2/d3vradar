import os, hmac, re, asyncio
from urllib.parse import urlsplit
import jwt
from fastapi import Request
from fastapi.responses import JSONResponse
from .store import workspace_context,ensure_workspace

MODE=os.getenv('RADAR_AUTH_MODE','cloudflare')
ORIGIN=os.getenv('RADAR_ORIGIN','https://radar.example.com').rstrip('/')
TEAM=os.getenv('CF_ACCESS_TEAM','').strip()
AUD=os.getenv('CF_ACCESS_AUD','').strip()
ALLOWED={x.strip().lower() for x in os.getenv('RADAR_ALLOWED_EMAILS','').split(',') if x.strip()}
LOCAL_TOKEN=os.getenv('RADAR_LOCAL_TOKEN','')
CLIENT=None

def validate_config():
    if MODE not in ('cloudflare','local'):raise RuntimeError('Unknown RADAR_AUTH_MODE')
    if MODE=='cloudflare':
        if not re.fullmatch(r'[a-z0-9-]+\.cloudflareaccess\.com',TEAM) or not AUD or not ALLOWED:
            raise RuntimeError('Set CF_ACCESS_TEAM (team.cloudflareaccess.com), CF_ACCESS_AUD and RADAR_ALLOWED_EMAILS. Access fails closed until configured.')
    elif len(LOCAL_TOKEN)<24:raise RuntimeError('Local development requires a random RADAR_LOCAL_TOKEN of at least 24 characters.')

def authenticate(request:Request):
    global CLIENT
    if MODE=='local':
        token=request.headers.get('authorization','').removeprefix('Bearer ')
        return 'local' if token and hmac.compare_digest(token,LOCAL_TOKEN) else None
    token=request.headers.get('Cf-Access-Jwt-Assertion','')
    if not token:return False
    try:
        if CLIENT is None:CLIENT=jwt.PyJWKClient(f'https://{TEAM}/cdn-cgi/access/certs',cache_keys=True,lifespan=300,timeout=5)
        key=CLIENT.get_signing_key_from_jwt(token)
        claims=jwt.decode(token,key.key,algorithms=['RS256'],audience=AUD,issuer=f'https://{TEAM}',options={'require':['exp','iat','iss','aud','email']})
        email=claims.get('email')
        if not isinstance(email,str) or not re.fullmatch(r'[^\s@]+@[^\s@]+',email):return None
        email=email.lower()
        return email if email in ALLOWED else None
    except (jwt.PyJWTError,ValueError,OSError):return False

async def guard(request,call_next):
    if request.url.path=='/health':return await call_next(request)
    # Static shell contains no personal data; all data, uploads and downloads require auth.
    if request.url.path.startswith('/api/'):
        identity=await asyncio.to_thread(authenticate,request)
        if not identity:return JSONResponse({'detail':'Sign in through Cloudflare Access to open this workspace.'},401)
        if request.method not in ('GET','HEAD','OPTIONS'):
            origin=request.headers.get('origin','')
            if origin!=ORIGIN:return JSONResponse({'detail':'Request origin was not accepted.'},403)
    if request.url.path.startswith('/api/'):
        await asyncio.to_thread(ensure_workspace,identity)
        request.state.identity=identity
        with workspace_context(identity):response=await call_next(request)
    else:response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-src https://www.google.com/maps/embed/ https://job-boards.greenhouse.io https://jobs.ashbyhq.com; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    if request.url.path.startswith('/api/'):response.headers['Cache-Control']='no-store'
    return response
