import hashlib,json,time,uuid
from .store import db,seal,unseal,get_setting,get_job,DEFAULT_PROFILE,DEFAULT_SEARCH
from .documents import prepare_resume,cover_letter,followup

def active_document(kind):
    with db() as c:r=c.execute('SELECT * FROM documents WHERE kind=? AND active=1 ORDER BY created DESC LIMIT 1',(kind,)).fetchone()
    return unseal(r['payload']) if r else None

def prepare(job_id):
    job=get_job(job_id)
    if not job:raise ValueError('Job not found')
    if not job.get('verified',True):raise ValueError('Paste and save the full job description before tailoring an indexed result.')
    if len(job.get('description',''))<80:raise ValueError('A full job description is needed before tailoring.')
    resume=active_document('resume')
    if not resume:raise ValueError('Upload and activate a base resume in Documents first.')
    base=active_document('cover');profile=get_setting('profile',DEFAULT_PROFILE)
    public_profile={k:profile.get(k,'') for k in ['name','email','location']}
    fingerprint=hashlib.sha256(json.dumps([resume['text'],(base or {}).get('text',''),job['description'],job['title'],job['company'],public_profile],sort_keys=True).encode()).hexdigest()
    with db() as c:
        prior=[{'id':r['id'],'kind':r['kind'],**unseal(r['payload'])} for r in c.execute('SELECT * FROM drafts WHERE job_id=?',(job_id,))]
    if prior and len([r for r in prior if r.get('fingerprint')==fingerprint])>=2:return [r for r in prior if r.get('fingerprint')==fingerprint]
    tailored,report=prepare_resume(resume['text'],job);letter,mode=cover_letter(resume['text'],(base or {}).get('text',''),job,public_profile)
    created=[]
    with db() as c:
        for kind,text in [('resume',tailored),('cover',letter)]:
            id=uuid.uuid4().hex;payload={'text':text,'fingerprint':fingerprint,'report':report,'mode':'Facts preserved; matched keywords highlighted and adjacent bullets ranked' if kind=='resume' else mode,'resume_source_id':resume.get('id'),'cover_source_id':(base or {}).get('id'),'reviewed':False}
            c.execute('INSERT INTO drafts VALUES(?,?,?,?,?,0)',(id,job_id,kind,seal(payload),time.time()));created.append({'id':id,'kind':kind,**payload})
    return created

def prepare_followup(job_id):
    j=get_job(job_id)
    if not j:raise ValueError('Job not found')
    with db() as c:r=c.execute('SELECT * FROM applications WHERE job_id=?',(job_id,)).fetchone()
    if not r or not r['applied']:raise ValueError('Mark the job as applied before creating a follow-up.')
    text=followup(j,get_setting('profile',DEFAULT_PROFILE),r['applied'])
    id=uuid.uuid4().hex;payload={'text':text,'mode':'Follow-up draft for review','reviewed':False}
    with db() as c:c.execute('INSERT INTO drafts VALUES(?,?,?,?,?,0)',(id,job_id,'followup',seal(payload),time.time()))
    return {'id':id,'kind':'followup',**payload}

def drain_queue(limit=5):
    if not active_document('resume'):return
    with db() as c:rows=c.execute("SELECT job_id FROM queue WHERE status='pending' LIMIT ?",(limit,)).fetchall()
    search=get_setting('search',DEFAULT_SEARCH)
    terms=set(search['keywords'].lower().split())
    for row in rows:
        j=get_job(row['job_id'])
        if not j:continue
        # Prepare matches to the saved search, rather than unrelated board listings.
        if (search['workplace']!='all' and j.get('workplace')!=search['workplace']) or not terms.intersection(j['title'].lower().split()):
            with db() as c:c.execute("UPDATE queue SET status='skipped' WHERE job_id=?",(j['id'],))
            continue
        try:
            prepare(j['id'])
            with db() as c:c.execute("UPDATE queue SET status='done',error='' WHERE job_id=?",(j['id'],))
        except ValueError as e:
            with db() as c:c.execute("UPDATE queue SET status='error',error=? WHERE job_id=?",(str(e),j['id']))


def draft_due_followups(limit=5):
    with db() as c:
        rows=c.execute("SELECT a.job_id FROM applications a WHERE a.status='applied' AND a.followup IS NOT NULL AND a.followup<=? AND NOT EXISTS (SELECT 1 FROM drafts d WHERE d.job_id=a.job_id AND d.kind='followup' AND d.created>=COALESCE(a.applied,0)) LIMIT ?",(time.time(),limit)).fetchall()
    for row in rows:prepare_followup(row['job_id'])
