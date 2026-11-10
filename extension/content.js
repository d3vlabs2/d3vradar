(()=>{
 if(globalThis.__radarHelperInstalled)return;globalThis.__radarHelperInstalled=true;
 function questionFor(el){
  const fieldset=el.closest('fieldset');
  const legend=fieldset?.querySelector('legend')?.innerText;
  if(legend)return legend;
  const labelled=el.getAttribute('aria-labelledby');
  if(labelled){const text=labelled.split(/\s+/).map(id=>document.getElementById(id)?.innerText||'').join(' ');if(text.trim())return text}
  if(el.getAttribute('aria-label'))return el.getAttribute('aria-label');
  if(el.labels?.length&&el.type!=='radio')return [...el.labels].map(x=>x.innerText).join(' ');
  return el.closest('[role="group"],[role="radiogroup"]')?.getAttribute('aria-label')||'';
 }
 function visible(el){return !!(el.getClientRects().length)&&!el.disabled}
 chrome.runtime.onMessage.addListener((message,sender,respond)=>{
  if(message.action!=='fill-radar-answers')return;
  const profile=message.answers;let filled=0;const skipped=[];const groups=new Map();
  for(const el of document.querySelectorAll('select,input[type="radio"]')){
   if(!visible(el))continue;
   if(el.type==='radio'){
    if(!el.name){skipped.push('Radio group without a name');continue}
    // Form identity prevents combining similarly named radio groups across forms.
    const formIndex=[...document.forms].indexOf(el.form),key=formIndex+':'+el.name;
    if(!groups.has(key))groups.set(key,[]);groups.get(key).push(el);continue;
   }
   const q=questionFor(el);const options=[...el.options];const answer=RadarMatcher.choose(q,options.map(o=>o.textContent),profile);
   if(answer.index>=0){const option=options[answer.index];if(option.disabled)continue;const setter=Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set;setter.call(el,option.value);el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));filled++}
   else if(RadarMatcher.category(q))skipped.push(q);
  }
  for(const els of groups.values()){
   const q=questionFor(els[0]);const labels=els.map(el=>el.labels?.length?[...el.labels].map(l=>l.innerText).join(' '):el.getAttribute('aria-label')||'');
   const answer=RadarMatcher.choose(q,labels,profile);
   if(answer.index>=0){els[answer.index].click();filled++}else if(RadarMatcher.category(q))skipped.push(q);
  }
  // No text entry, uploading, navigation, attestations, or submit actions occur.
  respond({filled,skipped:skipped.slice(0,12),note:'Review all answers before continuing. Custom controls and iframe questions may need manual answers.'});
 });
})();
