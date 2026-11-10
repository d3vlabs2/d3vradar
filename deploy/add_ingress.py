#!/usr/bin/env python3
"""Add the Radar route to an existing locally managed cloudflared config."""
import argparse,datetime,os,re,shutil,tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('config',nargs='?',default='/etc/cloudflared/config.yml');p.add_argument('--hostname',required=True);args=p.parse_args();path=Path(args.config)
if not re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?',args.hostname):raise SystemExit('Invalid hostname')
text=path.read_text();stat=path.stat()
if re.search(r'hostname:\s*[\"\']?'+re.escape(args.hostname)+r'(?:[\"\']?\s|$)',text):raise SystemExit('Radar already exists in the tunnel config. No changes made.')
if not re.search(r'^ingress:\s*$',text,re.M):raise SystemExit('No ingress list found. No changes made.')
# Insert before the catch-all. Existing routes, credentials and tunnel ID are untouched.
match=re.search(r'^([ \t]*)-\s+service:\s*[\"\']?http_status:404[\"\']?\s*$',text,re.M)
if not match:raise SystemExit('Could not identify the final http_status:404 rule. No changes made; add the documented rule manually.')
indent=match.group(1);rule=f'{indent}- hostname: {args.hostname}\n{indent}  service: http://127.0.0.1:3740\n\n'
backup=path.with_name(path.name+'.radar-backup-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'));shutil.copy2(path,backup)
fd,tmp=tempfile.mkstemp(prefix='.radar-',dir=path.parent)
try:
    with os.fdopen(fd,'w') as f:f.write(text[:match.start()]+rule+text[match.start():])
    os.chmod(tmp,stat.st_mode);os.chown(tmp,stat.st_uid,stat.st_gid);os.replace(tmp,path)
finally:
    if os.path.exists(tmp):os.unlink(tmp)
print('Added Radar ingress and preserved a timestamped backup. Validate before restarting cloudflared.')
tunnel=re.search(r'^tunnel:\s*[\"\']?([a-zA-Z0-9-]+)',text,re.M)
if tunnel:print('DNS route command: cloudflared tunnel route dns '+tunnel.group(1)+' '+args.hostname)
