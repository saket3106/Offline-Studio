import {test,expect} from '@playwright/test';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const axePath=require.resolve('axe-core/axe.min.js');
test.beforeEach(async({page})=>{await page.route('**/*',route=>{const u=new URL(route.request().url());return ['127.0.0.1','localhost'].includes(u.hostname)||u.protocol==='data:'?route.continue():route.abort();});});
test('mock desktop navigation, custom dropdown and keyboard palette',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto('/?mock');await expect(page.locator('.composer-shell')).toBeVisible();
 await page.getByRole('navigation',{name:'Primary destinations'}).getByRole('button',{name:'Image Studio',exact:true}).click();
 await page.getByRole('combobox',{name:'Studio canvas'}).click();await page.getByRole('option',{name:/Square/}).click();
 await expect(page.getByRole('combobox',{name:'Studio canvas'})).toContainText('Square');
 await page.keyboard.press('Control+k');await expect(page.getByRole('dialog')).toBeVisible();await page.getByRole('textbox',{name:'Search commands'}).fill('models');await page.keyboard.press('Enter');await expect(page.locator('.model-manager')).toBeVisible();
 expect(errors).toEqual([]);
});
test('5000-image and 5000-chat fixtures mount bounded windows and reach the end',async({page})=>{
 await page.goto('/?mock&stress');await expect(page.locator('.history-row').first()).toBeVisible();expect(await page.locator('.history-row').count()).toBeLessThan(50);
 await page.getByRole('navigation',{name:'Primary destinations'}).getByRole('button',{name:'Library',exact:true}).click();await expect(page.locator('.library-card').first()).toBeVisible();expect(await page.locator('.library-card').count()).toBeLessThan(60);
 await page.locator('.library-grid-scroll').evaluate(e=>e.scrollTop=e.scrollHeight);await expect.poll(()=>page.locator('.library-card').count()).toBeGreaterThan(0);await expect(page.locator('.library-card').last()).toHaveAttribute('aria-label',/4999/);
 await page.locator('.history-viewport').evaluate(e=>e.scrollTop=e.scrollHeight);await expect(page.locator('.history-row').last()).toContainText('4999');
});
test('accessibility: core screens have no serious or critical axe findings in either theme',async({page})=>{
 await page.goto('/?mock');await expect(page.locator('.composer-shell')).toBeVisible();
 for(const theme of ['dark','light']){
  await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);
  for(const name of ['Chats','Library','Image Studio','Models']){
   await page.getByRole('navigation',{name:'Primary destinations'}).getByRole('button',{name,exact:true}).click();
   if(name==='Models'){await expect(page.locator('.model-manager')).toHaveAttribute('aria-busy','false');await expect(page.locator('.model-manager-toolbar .primary-button')).toHaveCSS('opacity','1');}
   await page.addScriptTag({path:axePath});const result=await page.evaluate(async()=>window.axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa','wcag22aa']}}));
   const failures=result.violations.filter(v=>['serious','critical'].includes(v.impact)).map(v=>({id:v.id,targets:v.nodes.map(n=>n.target)}));expect(failures,`${theme}/${name}`).toEqual([]);
  }
 }
});
test('UI kit is development-only and supports keyboard focus',async({page})=>{await page.goto('/__ui-kit');await expect(page.getByRole('heading',{name:/UI kit/})).toBeVisible();await page.keyboard.press('Tab');await expect(page.getByRole('button',{name:'Primary',exact:true})).toBeFocused();});
test('New Chat is a client draft until send; repeated clicks do not persist empty chats',async({page})=>{
 await page.goto('/?mock');await expect(page.locator('.composer-shell')).toBeVisible();
 const count=()=>page.evaluate(()=>new Promise(r=>window.offlineBridge.getChats(raw=>r(JSON.parse(raw).length))));const before=await count();
 await page.locator('.new-chat-button').click();await page.locator('.new-chat-button').click();expect(await count()).toBe(before);
 await page.getByRole('textbox',{name:'Message input'}).fill('A synthetic streaming check');await page.keyboard.press('Enter');await expect.poll(count).toBe(before+1);await expect(page.locator('.assistant-message').last()).toContainText('mock adapter');
 await page.getByRole('button',{name:'Stop generation'}).click();await expect(page.getByRole('button',{name:'Send message'})).toBeVisible();
});
test('diagnostic drawer stays within viewport and restores focus after Escape',async({page})=>{
 await page.goto('/?mock');await expect(page.locator('.assistant-message')).toBeVisible();const trigger=page.getByRole('button',{name:'Response details'});await trigger.click();await expect(page.getByRole('dialog')).toBeVisible();
 expect(await page.locator('.response-drawer').evaluate(e=>e.scrollWidth<=e.clientWidth)).toBe(true);await page.keyboard.press('Escape');await expect(page.getByRole('dialog')).not.toBeVisible();await expect(trigger).toBeFocused();
});
test('small Studio uses one page scroller instead of clipping prompt controls',async({page})=>{
 await page.setViewportSize({width:960,height:600});await page.goto('/?mock');await page.getByRole('navigation',{name:'Primary destinations'}).getByRole('button',{name:'Image Studio',exact:true}).click();
 expect(await page.locator('.studio-controls').evaluate(e=>e.scrollHeight<=e.clientHeight+1)).toBe(true);await page.getByRole('combobox',{name:'Studio canvas'}).scrollIntoViewIfNeeded();await expect(page.getByRole('combobox',{name:'Studio canvas'})).toBeInViewport();
});
