import os, sqlite3, json, time, hashlib, hmac
from contextvars import ContextVar
from threading import RLock
from pathlib import Path
from contextlib import contextmanager, nullcontext
from cryptography.fernet import Fernet

DATA=Path(os.environ.get('RADAR_DATA','./data'))
DATA.mkdir(parents=True,exist_ok=True)
os.chmod(DATA,0o700)
key=os.environ.get('RADAR_ENCRYPTION_KEY')
if not key:
    raise RuntimeError('RADAR_ENCRYPTION_KEY must be set. Run deploy/configure.py first.')
CIPHER=Fernet(key.encode())
DB_PATH=DATA/'radar.sqlite'
CURRENT_WORKSPACE=ContextVar('radar_workspace',default=None)
OWNER_EMAIL=None
REGISTRY=DATA/'workspaces.sqlite'
WORKSPACE_LOCK=RLock()

@contextmanager
def registry():
    c=sqlite3.connect(REGISTRY,timeout=30)
    c.row_factory=sqlite3.Row
    try:
        c.executescript('CREATE TABLE IF NOT EXISTS metadata(id TEXT PRIMARY KEY,payload BLOB NOT NULL); CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email BLOB NOT NULL); CREATE TABLE IF NOT EXISTS members(id TEXT PRIMARY KEY,payload BLOB NOT NULL); CREATE TABLE IF NOT EXISTS public_feeds(id TEXT PRIMARY KEY,payload BLOB NOT NULL,created REAL NOT NULL);')
        os.chmod(REGISTRY,0o600)
        yield c
        c.commit()
    except Exception:
        c.rollback();raise
    finally:c.close()

def configure_workspaces(mode,allowed,owner=''):
    # The owner is chosen by server configuration, never by the first visitor.
    global OWNER_EMAIL
    if mode=='local':
        OWNER_EMAIL='local';return
    owner=owner.strip().lower()
    with registry() as c:
        row=c.execute("SELECT payload FROM metadata WHERE id='owner'").fetchone()
        bound=unseal(row['payload']) if row else None
        if bound and owner and bound!=owner:
            raise RuntimeError('RADAR_OWNER_EMAIL differs from the persisted workspace owner. Ownership cannot be reassigned by changing the allowlist.')
        owner=bound or owner or (next(iter(allowed)) if len(allowed)==1 else '')
        if not owner or owner not in allowed:
            raise RuntimeError('Set RADAR_OWNER_EMAIL to the existing owner and include that email in RADAR_ALLOWED_EMAILS before enabling multiple users.')
        if not bound:c.execute("INSERT INTO metadata VALUES('owner',?)",(seal(owner),))
    OWNER_EMAIL=owner

def workspace_key(email):
    if not isinstance(email,str) or not email:raise RuntimeError('Verified workspace identity required')
    if OWNER_EMAIL is None:raise RuntimeError('Workspace owner has not been configured')
    return 'owner' if email.lower()==OWNER_EMAIL else hmac.new(key.encode(),email.lower().encode(),hashlib.sha256).hexdigest()

@contextmanager
def workspace_context(email):
    token=CURRENT_WORKSPACE.set(workspace_key(email))
    try:yield
    finally:CURRENT_WORKSPACE.reset(token)

def current_workspace():
    current=CURRENT_WORKSPACE.get()
    if current is None:
        if os.getenv('RADAR_AUTH_MODE')=='local':return 'owner'
        raise RuntimeError('Database access requires a verified workspace context')
    return current

def workspace_path():
    ident=current_workspace()
    if ident=='owner':return DB_PATH
    parent=DATA/'workspaces';parent.mkdir(mode=0o700,exist_ok=True)
    return parent/(ident+'.sqlite')

def ensure_workspace(email):
    # Called only after JWT + allowlist validation. Each DB keeps the existing schema.
    with WORKSPACE_LOCK,workspace_context(email):
        ident=current_workspace()
        with registry() as c:
            known=c.execute('SELECT 1 FROM users WHERE id=?',(ident,)).fetchone()
        if not known or not workspace_path().exists():
            init()
            existing_profile=get_setting('profile') is not None
            if get_setting('profile_reviewed') is None:put_setting('profile_reviewed',existing_profile)
            if get_setting('profile') is None:put_setting('profile',{**DEFAULT_PROFILE,'email':'' if email=='local' else email})
            if get_setting('search') is None:put_setting('search',DEFAULT_SEARCH)
            with registry() as c:c.execute('INSERT OR REPLACE INTO users VALUES(?,?)',(ident,seal(email)))

def workspace_emails(allowed):
    with registry() as c:emails=[unseal(r['email']) for r in c.execute('SELECT email FROM users')]
    return [email for email in emails if email in allowed]

def cached_public_feed(cache_key):
    with registry() as c:row=c.execute('SELECT payload FROM public_feeds WHERE id=? AND created>?',(cache_key,time.time()-43200)).fetchone()
    return unseal(row['payload']) if row else None

def cache_public_feed(cache_key,jobs,snapshot):
    # Only connector responses enter this shared cache, never imports or personal records.
    with registry() as c:
        c.execute('DELETE FROM public_feeds WHERE created<?',(time.time()-43200,))
        c.execute('INSERT OR REPLACE INTO public_feeds VALUES(?,?,?)',(cache_key,seal([jobs,snapshot]),time.time()))


def seal(value):
    return CIPHER.encrypt(json.dumps(value,ensure_ascii=False).encode())
def unseal(value):
    return json.loads(CIPHER.decrypt(value))
@contextmanager
def db():
    c=sqlite3.connect(workspace_path(),timeout=30)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback(); raise
    finally:
        c.close()

def init():
    with db() as c:
        c.executescript('''
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS settings(id TEXT PRIMARY KEY,payload BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY,kind TEXT NOT NULL,name TEXT NOT NULL,payload BLOB NOT NULL,created REAL NOT NULL,active INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,source TEXT NOT NULL,payload TEXT NOT NULL,first_seen REAL NOT NULL,last_seen REAL NOT NULL,active INTEGER NOT NULL DEFAULT 1);
CREATE INDEX IF NOT EXISTS jobs_source ON jobs(source);
CREATE TABLE IF NOT EXISTS applications(job_id TEXT PRIMARY KEY REFERENCES jobs(id),status TEXT NOT NULL,notes BLOB NOT NULL,applied REAL,followup REAL,updated REAL NOT NULL);
CREATE TABLE IF NOT EXISTS tailored_resumes(document_id TEXT PRIMARY KEY REFERENCES documents(id),job_id TEXT NOT NULL REFERENCES jobs(id));
CREATE TABLE IF NOT EXISTS application_resumes(job_id TEXT PRIMARY KEY REFERENCES jobs(id),document_id TEXT NOT NULL REFERENCES documents(id));
CREATE TABLE IF NOT EXISTS drafts(id TEXT PRIMARY KEY,job_id TEXT NOT NULL REFERENCES jobs(id),kind TEXT NOT NULL,payload BLOB NOT NULL,created REAL NOT NULL,approved INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS source_runs(id TEXT PRIMARY KEY,checked REAL NOT NULL DEFAULT 0,success REAL NOT NULL DEFAULT 0,count INTEGER NOT NULL DEFAULT 0,error TEXT NOT NULL DEFAULT '',lease REAL NOT NULL DEFAULT 0,fingerprint TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS queue(job_id TEXT PRIMARY KEY REFERENCES jobs(id),status TEXT NOT NULL DEFAULT 'pending',error TEXT NOT NULL DEFAULT '');
''')
    with db() as c:
        if 'fingerprint' not in {r['name'] for r in c.execute('PRAGMA table_info(source_runs)')}:
            c.execute("ALTER TABLE source_runs ADD COLUMN fingerprint TEXT NOT NULL DEFAULT ''")
    os.chmod(workspace_path(),0o600)

def get_setting(key,default=None):
    with db() as c:r=c.execute('SELECT payload FROM settings WHERE id=?',(key,)).fetchone()
    return unseal(r['payload']) if r else default

def put_setting(key,value):
    with db() as c:c.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',(key,seal(value)))

DEFAULT_PROFILE={'name':'','email':'','location':'','home_address':'','veteran':False,'disability':False,'needs_sponsorship':False,'felony':False,'us_citizen':False,'authorized_us':False}
DEFAULT_SEARCH={'keywords':'IT support','location':'','workplace':'remote','auto_prepare':True,'followup_days':7,'scan_hours':12}

def get_job(job_id):
    with db() as c:r=c.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
    if not r:return None
    return {**json.loads(r['payload']),'firstSeen':r['first_seen'],'lastSeen':r['last_seen'],'active':bool(r['active'])}

def upsert_jobs(source,jobs,snapshot=False,connection=None):
    now=time.time()
    auto=get_setting('search',DEFAULT_SEARCH).get('auto_prepare')
    with (db() if connection is None else nullcontext(connection)) as c:
        if snapshot:c.execute('UPDATE jobs SET active=0 WHERE source=?',(source,))
        for j in jobs:
            c.execute('INSERT INTO jobs VALUES(?,?,?,?,?,1) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,last_seen=excluded.last_seen,active=1',(j['id'],source,json.dumps(j),now,now))
            if auto and j.get('description') and j.get('verified',True):
                c.execute("INSERT OR IGNORE INTO queue(job_id) VALUES(?)",(j['id'],))
    return len(jobs)


def save_imported_job(source,job,notes='',connection=None):
    # The listing and bookmark commit together; failure cannot leave a half-save.
    with (db() if connection is None else nullcontext(connection)) as c:
        upsert_jobs(source,[job],connection=c)
        old=c.execute('SELECT * FROM applications WHERE job_id=?',(job['id'],)).fetchone()
        status=old['status'] if old and old['status'] not in ('new','hidden') else 'saved'
        before=unseal(old['notes']) if old else ''
        note=before if not notes.strip() or notes.strip()==before else (before+'\n\n'+notes.strip()).strip()
        if len(note)>20000:raise ValueError('Combined notes exceed 20,000 characters. Edit the saved notes before importing again.')
        c.execute("INSERT INTO applications VALUES(?,?,?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET status=excluded.status,notes=excluded.notes,updated=excluded.updated",
                  (job['id'],status,seal(note),None,None,time.time()))
    return status
