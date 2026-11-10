(function(root){
 function normalize(s){return String(s||'').toLowerCase().replace(/[’']/g,'').replace(/[^a-z0-9]+/g,' ').trim()}
 function category(question){
  const q=normalize(question);
  // Do not fill questions whose polarity, compound conditions or scope is unclear.
  if(/\bif\b|\bunless\b|certify|attest|agree|consent|signature|not authorized|not legally|non citizen|noncitizen|misdemeanor|arrest|pending|ever had|citizenship other|another country|outside the|canadian|canada|united kingdom|uk citizen/.test(q))return null;
  if(/\b(veteran status|protected veteran|are you a veteran|military veteran)\b/.test(q)&&!/spouse|family|reserve|active duty/.test(q))return 'veteran';
  if(/disability|disabilities/.test(q)&&!/accommodation|family|history|previous|ever/.test(q))return 'disability';
  if(/sponsor|sponsorship/.test(q)&&/require|need|visa/.test(q)&&!/not require|no sponsorship|security clearance/.test(q))return 'needs_sponsorship';
  if(/felony|felonies/.test(q)&&!/misdemeanor|arrest|charges|past \d|last \d|within|years|months|since|during|expung|sealed|excluding/.test(q))return 'felony';
  if(/(us|u s|united states|american) citizen|citizen of the (us|u s|united states)/.test(q)&&!/permanent resident|green card|\bor\b|dual/.test(q))return 'us_citizen';
  if(/(authorized|authorised|eligible).*work.*(united states|\bus\b|u s\b)|work authorization.*(united states|\bus\b)/.test(q)&&!/without sponsorship|will you|proof|future|expiry|expire|until|duration/.test(q))return 'authorized_us';
  return null;
 }
 function choose(question,options,profile){
  const key=category(question);
  if(!key||typeof profile[key]!=='boolean')return {key:null,index:-1,reason:'Unrecognized or conditional question'};
  const yes=profile[key];const labels=options.map(normalize);
  const matches=[];
  for(let i=0;i<labels.length;i++){
   const label=labels[i];if(/prefer|decline|dont wish|do not wish|dont want|do not want|choose not|select|please choose/.test(label))continue;
   let match=false;
   if(key==='disability')match=yes?/^yes\b|^i have a disability$/.test(label):/^no\b|i do not have a disability|i dont have a disability|no i do not have a disability/.test(label);
   else if(key==='veteran')match=yes?/^yes$|^i am a protected veteran$|^protected veteran$/.test(label):/^no$|not a protected veteran|not a veteran|non veteran/.test(label);
   else match=yes?/^yes$|^yes i am$|^yes i do$|^yes i will$|^us citizen$|^u s citizen$/.test(label):/^no$|^no i am not$|^no i do not$|^no i will not$/.test(label);
   if(match)matches.push(i);
  }
  return {key,index:matches.length===1?matches[0]:-1,reason:matches.length===1?'Recognized standard answer':'Answer options need review'};
 }
 const api={normalize,category,choose};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.RadarMatcher=api;
})(globalThis);
