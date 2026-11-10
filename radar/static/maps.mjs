export function homeOrigin(profile={}){return String(profile.home_address||'').trim()||String(profile.location||'').trim();}
const vague=/^(remote|hybrid|on[ -]?site|worldwide|anywhere|global|united states(?: of america)?|usa?|u\.?s\.?a?\.?|canada|europe|emea|apac|americas|north america|united kingdom|uk|location not supplied|not supplied|unknown|multiple locations|various locations|texas)$/i;
export function destinations(job){
 const explicit=String(job.officeAddress||'').trim();
 if(explicit)return [{value:explicit,label:explicit,approximate:false}];
 if(job.workplace==='remote')return [];
 return [...new Set(String(job.location||'').split(/;|\n|\s\|\s/).map(s=>s.replace(/\b(remote|hybrid|on[ -]?site)\b/gi,'').replace(/^[\s,–—-]+|[\s,–—-]+$/g,'').trim()).filter(s=>s&&!vague.test(s)))].map(value=>({value,label:value,approximate:true}));
}
export function mapsUrl(destination,origin='',mode='driving'){
 if(!destination.trim())throw Error('Enter an office address or city first.');
 const allowed=['driving','walking','bicycling','transit'];if(!allowed.includes(mode))mode='driving';
 const route=Boolean(origin.trim());const url=new URL(route?'https://www.google.com/maps/dir/':'https://www.google.com/maps/search/');
 url.searchParams.set('api','1');url.searchParams.set(route?'destination':'query',destination.trim());
 if(route){url.searchParams.set('origin',origin.trim());url.searchParams.set('travelmode',mode);}
 return url.href;
}
export function embedUrl(key,destination,origin='',mode='driving'){
 if(!key||!destination.trim())return '';
 const url=new URL('https://www.google.com/maps/embed/v1/'+(origin.trim()?'directions':'place'));
 url.searchParams.set('key',key);url.searchParams.set(origin.trim()?'destination':'q',destination.trim());
 if(origin.trim()){url.searchParams.set('origin',origin.trim());url.searchParams.set('mode',['driving','walking','bicycling','transit'].includes(mode)?mode:'driving');url.searchParams.set('units','imperial');}
 return url.href;
}
