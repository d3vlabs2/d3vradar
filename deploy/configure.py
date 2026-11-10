#!/usr/bin/env python3
"""Create a private server .env; never overwrite an existing encryption key."""
import argparse,base64,os,re,secrets
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--local',action='store_true',help='Loopback-only development with a session token');args=p.parse_args()
root=Path(__file__).resolve().parents[1];env=root/'.env'
if env.exists():
    print('An .env already exists. Keeping its encryption key and settings. Edit it directly if needed.');raise SystemExit(0)
key=base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
if args.local:
    token=secrets.token_urlsafe(32)
    values={'RADAR_AUTH_MODE':'local','RADAR_ORIGIN':'http://localhost:3740','RADAR_LOCAL_TOKEN':token}
else:
    team=input('Cloudflare Access team domain (name.cloudflareaccess.com): ').strip().removeprefix('https://').rstrip('/')
    aud=input('Access application AUD tag: ').strip()
    email=input('Owner sign-in email: ').strip().lower()
    origin=input('Radar public origin (https://radar.example.com): ').strip().rstrip('/')
    if not re.fullmatch(r'https://[a-zA-Z0-9.-]+',origin):raise SystemExit('Enter an HTTPS origin without a path.')
    if not re.fullmatch(r'[a-z0-9-]+\.cloudflareaccess\.com',team) or not re.fullmatch(r'[a-zA-Z0-9_-]+',aud) or not re.fullmatch(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+',email):raise SystemExit('Enter the Access application details before starting the protected service.')
    values={'RADAR_AUTH_MODE':'cloudflare','RADAR_ORIGIN':origin,'CF_ACCESS_TEAM':team,'CF_ACCESS_AUD':aud,'RADAR_OWNER_EMAIL':email,'RADAR_ALLOWED_EMAILS':email}
values.update(RADAR_ENCRYPTION_KEY=key,RADAR_SCHEDULER='true',BRAVE_SEARCH_API_KEY='')
fd=os.open(env,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
with os.fdopen(fd,'w') as f:f.write(''.join(k+'='+v+'\n' for k,v in values.items()))
print('Created .env with private file permissions. Keep a secure backup of this file; its key is needed to decrypt your documents and profile.')
if args.local:print('Local preview URL: http://localhost:3740\nRead RADAR_LOCAL_TOKEN from .env and enter it in the local preview sign-in box. Do not publish local mode through the tunnel.')
