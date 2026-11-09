import {test,expect} from '@playwright/test';
import {writeFileSync} from 'node:fs';
test('bounded mock scroll measurements and warm route latency',async({page})=>{
 await page.route('**/*',route=>new URL(route.request().url()).hostname==='127.0.0.1'?route.continue():route.abort());
 await page.goto('/?mock&stress');await expect(page.locator('.history-row').first()).toBeVisible();
 const measure=selector=>page.locator(selector).evaluate(async element=>{
  const gaps=[];let previous=performance.now();for(let i=0;i<24;i++){await new Promise(requestAnimationFrame);const now=performance.now();gaps.push(now-previous);previous=now;element.scrollTop+=140;}
  const sorted=[...gaps].sort((a,b)=>a-b);return {frames:gaps.length,meanFrameMs:gaps.reduce((a,b)=>a+b)/gaps.length,p95FrameMs:sorted[Math.floor(sorted.length*.95)],maxFrameMs:Math.max(...gaps)};
 });
 const sidebar=await measure('.history-viewport');await page.getByRole('navigation',{name:'Primary destinations'}).getByRole('button',{name:'Library',exact:true}).click();await expect(page.locator('.library-card').first()).toBeVisible();const library=await measure('.library-grid-scroll');
 const started=performance.now();const modelsReadyInPageMs=await page.evaluate(()=>new Promise((resolve,reject)=>{const begin=performance.now();let timeout;const observer=new MutationObserver(()=>{if(document.querySelector('.model-manager[aria-busy=false]')){observer.disconnect();clearTimeout(timeout);resolve(performance.now()-begin);}});observer.observe(document.body,{childList:true,attributes:true,subtree:true});timeout=setTimeout(()=>{observer.disconnect();reject(Error('Models route did not become ready'));},4000);[...document.querySelectorAll('.side-primary button')].find(b=>b.textContent.trim()==='Models').click();}));const modelsSwitchControllerWallMs=performance.now()-started;
 const result={scope:'Headless Edge, 5000 synthetic chats/images, 24 rAF scroll frames each. In-page Models readiness includes mock data arrival; controller wall includes automation overhead. Not native inference or a guarantee of 60fps on every machine.',sidebar,library,modelsReadyInPageMs,modelsSwitchControllerWallMs};writeFileSync('../docs/ui-performance.json',JSON.stringify(result,null,2));expect(sidebar.frames).toBe(24);expect(library.frames).toBe(24);
});
