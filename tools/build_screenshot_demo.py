from pathlib import Path
import json,time,base64
import sys
r=Path(__file__).resolve().parents[1];now=time.time()
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
fixtures=[('IT Support Specialist','Northstar Demo Labs','Remote, United States','remote','remotive'),('Systems Administrator','Example Cloudworks','Albany, NY','hybrid','greenhouse'),('Service Desk Analyst','Sample Health Systems','Remote, United States','remote','remoteok'),('Infrastructure Engineer','Demo Network Group','Buffalo, NY','hybrid','ashby'),('Desktop Support Technician','Example Operations','Rochester, NY','onsite','manual')]
jobs=[dict(id='demo-'+str(i),title=t,company=c,location=l,workplace=w,source=s,url='https://example.com/demo',description='Demonstration listing only. Support Windows and Linux workstations, troubleshoot network access, maintain Active Directory accounts, document service requests, and collaborate with a friendly IT team.',verified=True,active=True,applicants=None,salary='$65,000–$90,000',firstSeen=now-i*86400,lastSeen=now) for i,(t,c,l,w,s) in enumerate(fixtures)]
sources=[dict(id=s,name=n,url=u,searchUrl=u,mode='feed',automatic=True,count=0,about=a,application=dict(mode='external',reason='Review application support on each employer listing.')) for s,n,u,a in [('remotive','Remotive','https://remotive.com','Remote opportunities from a public job feed.'),('greenhouse','Greenhouse discovery','https://www.greenhouse.com/for-job-seekers','Employer job boards and application options.'),('ashby','Ashby careers','https://www.ashbyhq.com/careers','Public employer listings on Ashby.'),('remoteok','Remote OK','https://remoteok.com','Remote roles and searchable job discovery.'),('dice','Dice','https://www.dice.com','Technology job discovery and manual imports.'),('linkedin','LinkedIn','https://www.linkedin.com/jobs','Indexed discovery and external applications.')]]
state=dict(identity=dict(email='demo@example.test',privateWorkspace=True,mode='cloudflare',isOwner=True),jobs=jobs,applications=[dict(job_id='demo-1',status='applied',notes='Demo application record.',applied=now-8*86400,followup=now-86400),dict(job_id='demo-2',status='interviewing',notes='Demo interview record.',applied=now-5*86400),dict(job_id='demo-3',status='saved',notes='')],profile=dict(name='Demo Workspace',location='Albany, NY',home_address='Albany, NY'),search=dict(keywords='IT support systems',location='',workplace='all'),queue=dict(pending=0),scheduler=False,documents=[],drafts=[],sources=sources,mapsEmbedKey='')
js=(r/'radar/static/app.js').read_text()
for name in ['maps','stats']:
 uri='data:text/javascript;base64,'+base64.b64encode((r/f'radar/static/{name}.mjs').read_bytes()).decode()
 js=js.replace('./'+name+'.mjs?v=2.8.2',uri)
js=js.replace("sessionStorage.getItem('radar-dev-token')","''")
setup='const DEMO='+json.dumps(state)+r""";
if(new URLSearchParams(location.search).has('guest')){DEMO.identity.isOwner=false;DEMO.identity.email='guest@example.test';}
const DEMO_USERS=[{id:'owner',email:'demo@example.test',isOwner:true,enabled:true,registered:true}];
window.fetch=async(url,options={})=>{
 const path=String(url).split('?')[0],method=options.method||'GET';let result={drafts:[]};
 if(path.endsWith('/workspace'))result=DEMO;
 else if(path.endsWith('/import/fetch'))result={...DEMO.jobs[0],title:'Imported Demo Support',company:'Example Import Demo',method:'Demo public extraction'};
 else if(path.endsWith('/jobs')&&method==='POST'){
  const input=JSON.parse(options.body),job={...input,id:'demo-import-'+DEMO.jobs.length,active:true,verified:true,firstSeen:Date.now()/1000};DEMO.jobs.push(job);DEMO.applications.push({job_id:job.id,status:'saved',notes:input.notes||'',applied:null,followup:null});result={job,savedTo:'saved'};
 }
 else if(path.includes('/applications/')&&method==='PUT'){
  const row=DEMO.applications.find(row=>path.endsWith('/'+row.job_id));Object.assign(row,JSON.parse(options.body));result={ok:true};
 }
 else if(path.endsWith('/profile')&&method==='PUT'){DEMO.profile=JSON.parse(options.body);result={ok:true};}
 else if(path.endsWith('/admin/users')&&method==='GET')result={users:DEMO_USERS,cloudflarePolicyManaged:false};
 else if(path.endsWith('/admin/users')&&method==='POST'){
  const user={id:'demo-member-'+DEMO_USERS.length,email:JSON.parse(options.body).email,isOwner:false,enabled:true,registered:false};DEMO_USERS.push(user);result={user};
 }else if(path.includes('/admin/users/')&&method==='PUT'){
  const user=DEMO_USERS.find(user=>path.endsWith('/'+user.id));user.enabled=JSON.parse(options.body).enabled;result={user};
 }
 return {ok:true,status:200,json:async()=>result};
};"""
html='<!doctype html><html lang="en"><head><meta charset="utf-8"><title>D3V Radar · Demo screenshots</title><style>'+(r/'radar/static/style.css').read_text()+'</style></head><body><div id="app"></div><div id="overlay"></div><div id="toast"></div><script>'+setup+'</script><script type="module">'+js+'</script></body></html>'
(out/'index.html').write_text(html)
