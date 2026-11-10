// Render the real Radar UI with fictional fixtures; never connects to a homelab.
const {chromium}=require('playwright');
const fs=require('node:fs');
(async()=>{
 fs.mkdirSync('docs/screenshots',{recursive:true});
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1200},deviceScaleFactor:1});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:5173');
 await page.locator('.job-card').first().waitFor();await page.evaluate(()=>document.fonts.ready);
 await page.screenshot({path:'docs/screenshots/discover.png'});
 await page.locator('[data-tab="2"]').click();await page.screenshot({path:'docs/screenshots/applications.png'});
 await page.locator('[data-tab="0"]').click();await page.locator('[data-map="demo-1"]').click();
 await page.locator('[role="dialog"]').waitFor();await page.screenshot({path:'docs/screenshots/commute.png'});
 await page.keyboard.press('Escape');await page.locator('[data-tab="3"]').click();
 await page.locator('.source-card').first().waitFor();await page.screenshot({path:'docs/screenshots/sources.png'});
 await browser.close();if(errors.length)throw Error(errors.join('\n'));
})();
