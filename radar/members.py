"""Owner-managed beta access. This does not modify Cloudflare's edge policy."""
import re
import time
from fastapi import HTTPException
from . import store


def normalize_email(value):
    email=value.strip().lower()
    if len(email)>254 or not re.fullmatch(r'[a-z0-9._%+-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}',email):
        raise ValueError('Enter a complete sign-in email address.')
    local,domain=email.split('@')
    if len(local)>64 or local.startswith('.') or local.endswith('.') or '..' in local or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',label) for label in domain.split('.')):
        raise ValueError('Enter a complete sign-in email address.')
    return email


def allowed_emails(configured):
    allowed=set(configured)
    with store.registry() as c:
        records=[store.unseal(r['payload']) for r in c.execute('SELECT payload FROM members')]
    for row in records:
        if row['email']==store.OWNER_EMAIL:continue
        if row['enabled']:allowed.add(row['email'])
        else:allowed.discard(row['email'])
    return allowed


def permitted(email,configured):
    if email==store.OWNER_EMAIL:return email in configured
    with store.registry() as c:row=c.execute('SELECT payload FROM members WHERE id=?',(store.workspace_key(email),)).fetchone()
    return bool(store.unseal(row['payload'])['enabled']) if row else email in configured


def list_members(configured):
    with store.registry() as c:
        managed={store.unseal(r['payload'])['email']:store.unseal(r['payload']) for r in c.execute('SELECT payload FROM members')}
        registered={store.unseal(r['email']) for r in c.execute('SELECT email FROM users')}
    emails=set(configured)|set(managed)|registered|{store.OWNER_EMAIL}
    allowed=allowed_emails(configured)
    return [{'id':store.workspace_key(email),'email':email,'isOwner':email==store.OWNER_EMAIL,
             'enabled':email in allowed,'registered':email in registered,
             'created':managed.get(email,{}).get('created')} for email in sorted(emails) if email and email!='local']


def add_member(email,configured):
    email=normalize_email(email)
    with store.WORKSPACE_LOCK:
        if email==store.OWNER_EMAIL:raise HTTPException(409,'The owner already has access.')
        with store.registry() as c:
            ident=store.workspace_key(email)
            if c.execute('SELECT 1 FROM members WHERE id=?',(ident,)).fetchone() or email in configured:
                raise HTTPException(409,'This user is already listed. Use Enable or Disable to change access.')
            if c.execute('SELECT COUNT(*) FROM members').fetchone()[0]>=200:
                raise ValueError('The beta user limit has been reached.')
            c.execute('INSERT INTO members VALUES(?,?)',(ident,store.seal({'email':email,'enabled':True,'created':time.time()})))
    return next(row for row in list_members(configured) if row['email']==email)


def set_enabled(ident,enabled,configured):
    with store.WORKSPACE_LOCK:
        row=next((row for row in list_members(configured) if row['id']==ident),None)
        if not row:raise HTTPException(404,'User not found')
        if row['isOwner']:raise HTTPException(403,'The owner cannot be disabled or reassigned here.')
        with store.registry() as c:
            c.execute('INSERT OR REPLACE INTO members VALUES(?,?)',(ident,store.seal({'email':row['email'],'enabled':enabled,'created':row['created'] or time.time()})))
    return next(row for row in list_members(configured) if row['id']==ident)
