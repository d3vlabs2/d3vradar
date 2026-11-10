export function localDateKey(value=new Date()) {
  const date=value instanceof Date?value:new Date(value);
  if(!Number.isFinite(date.getTime()))return '';
  return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
}
export function defaultAppliedDate(status,current='',existingApplied=null,now=new Date()) {
  return status==='applied'&&!current&&!existingApplied?localDateKey(now):current;
}
export function timestampDateKey(value) {
  const n=Number(value);
  if(!Number.isFinite(n)||n<=0)return '';
  return localDateKey(new Date(n>1e12?n:n*1000));
}
export function buildTrendStats(jobs=[],applications=[],days=14,now=new Date()) {
  const span=days===30?30:14;
  const buckets=[];
  for(let offset=span-1;offset>=0;offset--) {
    const day=new Date(now.getFullYear(),now.getMonth(),now.getDate()-offset);
    buckets.push({key:localDateKey(day),label:day.toLocaleDateString(undefined,{month:'short',day:'numeric'}),listings:0,applications:0});
  }
  const lookup=new Map(buckets.map(b=>[b.key,b]));
  const seenJobs=new Set(),seenApps=new Set();let undatedApplications=0;
  for(const job of jobs) {
    if(seenJobs.has(job.id))continue;seenJobs.add(job.id);
    const key=timestampDateKey(job.firstSeen);if(lookup.has(key))lookup.get(key).listings++;
  }
  for(const app of applications) {
    if(seenApps.has(app.job_id))continue;seenApps.add(app.job_id);
    const key=timestampDateKey(app.applied);
    if(!key&&['applied','interviewing','rejected','offer','withdrawn'].includes(app.status))undatedApplications++;
    if(lookup.has(key))lookup.get(key).applications++;
  }
  return {buckets,days:span,undatedApplications,listings:buckets.reduce((s,b)=>s+b.listings,0),applications:buckets.reduce((s,b)=>s+b.applications,0)};
}
