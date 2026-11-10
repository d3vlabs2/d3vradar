import json
import pytest
from radar import store,security,members
from test_workspaces import tenants,OWNER,FRIEND
from test_app import JOB,RESUME

NEW='newfriend@example.test'


def test_only_owner_can_manage_users(tenants):
    c,h,_=tenants
    assert c.get('/api/workspace',headers=h()).json()['identity']['isOwner'] is True
    assert c.get('/api/workspace',headers=h(FRIEND)).json()['identity']['isOwner'] is False
    assert c.get('/api/admin/users',headers=h(FRIEND)).status_code==403
    assert c.post('/api/admin/users',headers=h(FRIEND),json={'email':NEW}).status_code==403
    assert c.put('/api/admin/users/owner',headers=h(FRIEND),json={'enabled':False}).status_code==403
    assert c.get('/api/admin/users').status_code==401
    owner=c.get('/api/admin/users',headers=h()).json()
    assert owner['cloudflarePolicyManaged'] is False
    assert any(row['email']==OWNER and row['isOwner'] for row in owner['users'])


def test_owner_can_invite_without_env_changes_and_guest_gets_empty_workspace(tenants):
    c,h,path=tenants
    assert c.get('/api/workspace',headers=h(NEW)).status_code==401
    r=c.post('/api/admin/users',headers=h(),json={'email':'  NewFriend@Example.Test  '})
    assert r.status_code==200,r.text
    user=r.json()['user']
    assert user['email']==NEW and user['enabled'] and not user['registered']
    assert NEW not in security.ALLOWED
    workspace=c.get('/api/workspace',headers=h(NEW)).json()
    assert workspace['identity']['email']==NEW and not workspace['identity']['isOwner']
    assert workspace['documents']==workspace['applications']==workspace['drafts']==workspace['jobs']==[]
    assert workspace['profile']['home_address']==''
    assert NEW.encode() not in store.REGISTRY.read_bytes()
    assert c.post('/api/admin/users',headers=h(),json={'email':NEW}).status_code==409
    # No profile contact field can turn a guest into an owner.
    c.put('/api/profile',headers=h(NEW),json={'name':'Guest Demo','email':OWNER})
    assert c.get('/api/admin/users',headers=h(NEW)).status_code==403
    assert c.get('/api/documents/legacy-document',headers=h(NEW)).status_code==404
    assert NEW in security.allowed_emails()
    assert NEW in store.workspace_emails(security.allowed_emails())


def test_disable_overrides_env_and_reenable_retains_workspace(tenants):
    c,h,_=tenants
    c.put('/api/profile',headers=h(FRIEND),json={'name':'Friend Preserved','home_address':'456 Example Road, Buffalo, NY'})
    rows=c.get('/api/admin/users',headers=h()).json()['users']
    friend=next(row for row in rows if row['email']==FRIEND)
    assert FRIEND in security.ALLOWED
    assert c.put('/api/admin/users/'+friend['id'],headers=h(),json={'enabled':False}).status_code==200
    assert c.get('/api/workspace',headers=h(FRIEND)).status_code==401
    assert FRIEND not in security.allowed_emails()
    assert FRIEND not in store.workspace_emails(security.allowed_emails())
    # A configuration reload preserves the encrypted disable override.
    store.configure_workspaces('cloudflare',security.ALLOWED,OWNER)
    assert c.get('/api/workspace',headers=h(FRIEND)).status_code==401
    assert c.put('/api/admin/users/'+friend['id'],headers=h(),json={'enabled':True}).status_code==200
    profile=c.get('/api/workspace',headers=h(FRIEND)).json()['profile']
    assert profile['name']=='Friend Preserved' and profile['home_address'].startswith('456 Example Road')


def test_owner_protected_and_unexpected_fields_rejected(tenants):
    c,h,_=tenants
    assert c.put('/api/admin/users/owner',headers=h(),json={'enabled':False}).status_code==403
    assert c.put('/api/admin/users/owner',headers=h(),json={'enabled':True}).status_code==403
    assert c.post('/api/admin/users',headers=h(),json={'email':OWNER}).status_code==409
    assert c.post('/api/admin/users',headers=h(),json={'email':NEW,'isOwner':True}).status_code==422
    assert c.post('/api/admin/users',headers=h(),json={'email':'not an email'}).status_code==400
    assert c.put('/api/admin/users/missing',headers=h(),json={'enabled':False}).status_code==404
    assert c.post('/api/admin/users',headers={**h(),'Origin':'https://evil.example.test'},json={'email':NEW}).status_code==403


def test_home_address_saved_trimmed_and_stays_out_of_public_contact_location(tenants):
    c,h,_=tenants
    value='123 Example Street, Apt #2, Albany, NY 12207'
    assert c.put('/api/profile',headers=h(),json={'name':'Owner Demo','home_address':'  '+value+'  ','location':'Albany, NY'}).status_code==200
    owner=c.get('/api/workspace',headers=h()).json()['profile']
    assert owner['home_address']==value and owner['location']=='Albany, NY'
    guest=c.get('/api/workspace',headers=h(FRIEND)).json()['profile']
    assert not guest.get('home_address')
    with store.workspace_context(OWNER):
        with store.db() as db:assert value.encode() not in db.execute("SELECT payload FROM settings WHERE id='profile'").fetchone()['payload']
    assert c.put('/api/profile',headers=h(),json={'name':'Owner Demo','home_address':'x'*301}).status_code==422
    c.post('/api/documents',headers=h(),data={'kind':'resume'},files={'file':('demo.txt',RESUME.encode(),'text/plain')})
    job=c.post('/api/jobs',headers=h(),json=JOB).json()['job']['id']
    drafted=c.post('/api/jobs/'+job+'/prepare',headers=h()).json()['drafts']
    assert all(value not in draft['text'] for draft in drafted)
