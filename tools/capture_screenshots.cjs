// Render the real Radar UI with fictional fixtures; never connects to a homelab.
const {chromium}=require('playwright');
const fs=require('node:fs');
(async()=>{
 fs.mkdirSync('docs/screenshots',{recursive:true});
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1200},deviceScaleFactor:1});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>{
  const interval=window.setInterval;
  window.setInterval=(callback,delay,...args)=>{
   if(delay===10000){window.refreshFixture=callback;return 0;}
   return interval(callback,delay,...args);
  };
 });
 await page.goto('http://127.0.0.1:5173');
 await page.locator('.job-card').first().waitFor();await page.evaluate(()=>document.fonts.ready);
 // Finish a background request after a filter has received focus.
 await page.evaluate(()=>{
  const fetchFixture=window.fetch;
  window.workplaceControl=document.querySelector('#work');
  window.fetch=async (...args)=>{
   await new Promise(resolve=>{window.finishRefresh=resolve;});
   return fetchFixture(...args);
  };
  window.refreshFixture();
  window.fetch=fetchFixture;
 });
 await page.locator('#work').click();
 await page.keyboard.press('Escape');
 await page.locator('#work').focus();
 await page.evaluate(async ()=>{
  window.finishRefresh();
  await new Promise(resolve=>requestAnimationFrame(resolve));
  if(document.querySelector('#work')!==window.workplaceControl)throw Error('Background refresh replaced an active filter');
 });
 await page.locator('#work').selectOption('hybrid');
 await page.locator('#sort').selectOption('newest');
 if(await page.locator('#job-locations option[value="Albany, NY"]').count()!==1)throw Error('Missing location suggestion');
 await page.locator('#where').fill('Albany');
 await page.getByRole('button',{name:'Search jobs',exact:true}).click();
 await page.getByText(/Search complete · 1 matches/).waitFor();
 if(await page.locator('.job-card').count()!==1||!await page.getByRole('button',{name:'Systems Administrator',exact:true}).isVisible())throw Error('Filters did not select the expected job');
 await page.getByRole('button',{name:'Reset filters',exact:true}).click();
 // Beta UI regression checks: identity, sign-out, and private search settings.
 if(!(await page.locator('.private').innerText()).includes('demo@example.test'))throw Error('Missing verified identity display');
 await page.getByRole('link',{name:'Sign out',exact:true}).waitFor();
 await page.locator('[data-tab="6"]').click();
 await page.locator('#settings-form input[name="keywords"]').waitFor();
 await page.locator('[data-tab="5"]').click();
 const home='123 Example Street, Apt #2, Albany, NY 12207';
 await page.getByLabel('Home address for directions',{exact:true}).fill(home);
 await page.getByRole('button',{name:'Save profile',exact:true}).click();
 await page.getByText('Saved.',{exact:true}).waitFor();
 await page.locator('[data-tab="7"]').click();
 await page.getByRole('heading',{name:'Add a beta user',exact:true}).waitFor();
 await page.getByLabel('Sign-in email',{exact:true}).fill('beta.friend@example.test');
 await page.getByRole('button',{name:'Add user',exact:true}).click();
 await page.locator('.member-row').filter({hasText:'beta.friend@example.test'}).waitFor();
 page.on('dialog',dialog=>dialog.accept());
 await page.getByRole('button',{name:'Disable',exact:true}).click();
 await page.getByRole('button',{name:'Enable',exact:true}).waitFor();
 await page.getByRole('button',{name:'Enable',exact:true}).click();
 await page.getByRole('button',{name:'Disable',exact:true}).waitFor();
 await page.screenshot({path:'docs/screenshots/users.png',fullPage:true});
 await page.locator('[data-tab="0"]').click();
 // Import, fetch, and save stay in one dialog. Saving returns to Saved jobs.
 await page.getByRole('button',{name:'Import job',exact:true}).click();
 await page.getByLabel('Job URL',{exact:true}).fill('https://example.test/one-dialog-import');
 await page.getByRole('button',{name:'Fetch job details',exact:true}).click();
 await page.getByText(/Details fetched/).waitFor();
 if(await page.getByLabel('Job title',{exact:true}).inputValue()!=='Imported Demo Support')throw Error('Fetched fields missing from import dialog');
 await page.getByLabel('Your notes (optional)',{exact:true}).fill('Demo note: review this role later.');
 await page.screenshot({path:'docs/screenshots/import.png',fullPage:true});
 await page.getByRole('button',{name:'Save to Saved jobs',exact:true}).click();
 await page.getByText('Saved to Saved jobs. Open it there whenever you are ready.',{exact:true}).waitFor();
 await page.locator('.nav.active[data-tab="1"]').waitFor();
 await page.getByRole('button',{name:'Imported Demo Support',exact:true}).waitFor();
 if(await page.locator('[role="dialog"]').count()!==0)throw Error('Import opened a second popup');
 await page.getByRole('button',{name:'Imported Demo Support',exact:true}).click();
 await page.locator('[role="dialog"] #application-form').waitFor();
 if(await page.getByPlaceholder('Recruiter, interview details, next steps…',{exact:true}).inputValue()!=='Demo note: review this role later.')throw Error('Imported notes did not persist');
 const today=await page.evaluate(()=>{const now=new Date();return `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;});
 if(await page.locator('#applied-date').inputValue()!==today)throw Error('Applied date was not prefilled with today');
 await page.getByText('Change this date if you applied on a different day.',{exact:true}).waitFor();
 await page.getByRole('button',{name:'Save application',exact:true}).click();
 await page.getByText('Application saved.',{exact:true}).waitFor();
 if(await page.locator('.stats > div').nth(1).locator('strong').innerText()!=='02')throw Error('Bookmark was incorrectly counted as an application');
 await page.locator('#applied-date').fill('2026-10-20');
 await page.locator('#application-status').selectOption('applied');
 await page.getByRole('button',{name:'Save application',exact:true}).click();
 await page.getByText('Application saved.',{exact:true}).waitFor();
 if(await page.locator('#applied-date').inputValue()!=='2026-10-20')throw Error('Edited application date was overwritten');

 await page.keyboard.press('Escape');
 await page.locator('[data-tab="0"]').click();
 await page.screenshot({path:'docs/screenshots/discover.png',fullPage:true});
 await page.locator('[data-tab="2"]').click();await page.screenshot({path:'docs/screenshots/applications.png'});
 await page.locator('[data-tab="0"]').click();await page.locator('[data-map="demo-1"]').click();
 await page.locator('[role="dialog"]').waitFor();
 if(await page.locator('.map-origin').inputValue()!==home)throw Error('Saved home address was not used');
 await page.getByRole('button',{name:'Directions from home',exact:true}).click();
 let route=new URL(await page.locator('.map-output a').getAttribute('href'));
 if(route.searchParams.get('origin')!==home)throw Error('Route did not use saved address');
 await page.locator('.map-origin').fill('Buffalo, NY');
 await page.getByRole('button',{name:'Directions from home',exact:true}).click();
 route=new URL(await page.locator('.map-output a').getAttribute('href'));
 if(route.searchParams.get('origin')!=='Buffalo, NY')throw Error('Route override was ignored');
 await page.getByRole('button',{name:'Edit saved home address in Profile',exact:true}).click();
 if(await page.getByLabel('Home address for directions',{exact:true}).inputValue()!==home)throw Error('Route override changed saved profile');
 await page.locator('[data-tab="0"]').click();await page.locator('[data-map="demo-1"]').click();
 await page.screenshot({path:'docs/screenshots/commute.png'});
 await page.keyboard.press('Escape');await page.locator('[data-tab="3"]').click();
 await page.locator('.source-card').first().waitFor();await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:'docs/screenshots/sources.png',fullPage:true});
 const guest=await browser.newPage();await guest.goto('http://127.0.0.1:5173/?guest=1');await guest.locator('.job-card').first().waitFor();if(await guest.locator('[data-tab="7"]').count()!==0)throw Error('Guest can see user management');await guest.close();
 await browser.close();if(errors.length)throw Error(errors.join('\n'));
})();
