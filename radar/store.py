import os, sqlite3, json, time
from pathlib import Path
from contextlib import contextmanager
from cryptography.fernet import Fernet

DATA=Path(os.environ.get('RADAR_DATA','./data'))
DATA.mkdir(parents=True,exist_ok=True)
os.chmod(DATA,0o700)
key=os.environ.get('RADAR_ENCRYPTION_KEY')
if not key:
    raise RuntimeError('RADAR_ENCRYPTION_KEY must be set. Run deploy/configure.py first.')
CIPHER=Fernet(key.encode())
DB_PATH=DATA/'radar.sqlite'

def seal(value):
    return CIPHER.encrypt(json.dumps(value,ensure_ascii=False).encode())
def unseal(value):
    return json.loads(CIPHER.decrypt(value))
@contextmanager
def db():
    c=sqlite3.connect(DB_PATH,timeout=30)
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
CREATE TABLE IF NOT EXISTS drafts(id TEXT PRIMARY KEY,job_id TEXT NOT NULL REFERENCES jobs(id),kind TEXT NOT NULL,payload BLOB NOT NULL,created REAL NOT NULL,approved INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS source_runs(id TEXT PRIMARY KEY,checked REAL NOT NULL DEFAULT 0,success REAL NOT NULL DEFAULT 0,count INTEGER NOT NULL DEFAULT 0,error TEXT NOT NULL DEFAULT '',lease REAL NOT NULL DEFAULT 0,fingerprint TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS queue(job_id TEXT PRIMARY KEY REFERENCES jobs(id),status TEXT NOT NULL DEFAULT 'pending',error TEXT NOT NULL DEFAULT '');
''')
    with db() as c:
        if 'fingerprint' not in {r['name'] for r in c.execute('PRAGMA table_info(source_runs)')}:
            c.execute("ALTER TABLE source_runs ADD COLUMN fingerprint TEXT NOT NULL DEFAULT ''")
    os.chmod(DB_PATH,0o600)

def get_setting(key,default=None):
    with db() as c:r=c.execute('SELECT payload FROM settings WHERE id=?',(key,)).fetchone()
    return unseal(r['payload']) if r else default

def put_setting(key,value):
    with db() as c:c.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',(key,seal(value)))

DEFAULT_PROFILE={'name':'','email':'','location':'','veteran':False,'disability':False,'needs_sponsorship':False,'felony':False,'us_citizen':False,'authorized_us':False}
DEFAULT_SEARCH={'keywords':'IT support','location':'','workplace':'remote','auto_prepare':True,'followup_days':7,'scan_hours':12}

def get_job(job_id):
    with db() as c:r=c.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
    if not r:return None
    return {**json.loads(r['payload']),'firstSeen':r['first_seen'],'lastSeen':r['last_seen'],'active':bool(r['active'])}

def upsert_jobs(source,jobs,snapshot=False):
    now=time.time()
    auto=get_setting('search',DEFAULT_SEARCH).get('auto_prepare')
    with db() as c:
        if snapshot:c.execute('UPDATE jobs SET active=0 WHERE source=?',(source,))
        for j in jobs:
            c.execute('INSERT INTO jobs VALUES(?,?,?,?,?,1) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,last_seen=excluded.last_seen,active=1',(j['id'],source,json.dumps(j),now,now))
            if auto and j.get('description') and j.get('verified',True):
                c.execute("INSERT OR IGNORE INTO queue(job_id) VALUES(?)",(j['id'],))
    return len(jobs)
