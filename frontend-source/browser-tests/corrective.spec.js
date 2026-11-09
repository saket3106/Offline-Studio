import {test,expect} from '@playwright/test';

test('Settings stays centered, bounded and scrollable at desktop sizes and scaling',async({page})=>{
 for(const viewport of [{width:1366,height:768},{width:1920,height:1080},{width:1280,height:720},{width:911,height:512}]){
  await page.setViewportSize(viewport);await page.goto('/?mock');
  await page.getByRole('button',{name:'Settings',exact:true}).first().click();
  const popup=page.locator('.settings-dialog');await expect(popup).toBeVisible();
  const box=await popup.boundingBox();expect(box.y).toBeGreaterThanOrEqual(0);expect(box.y+box.height).toBeLessThanOrEqual(viewport.height);
  await expect(popup.locator('.dialog-footer')).toBeInViewport();
  expect(await popup.locator('.settings-content').evaluate(e=>getComputedStyle(e).overflowY)).toBe('auto');
 }
});

test('one image job retains its preview footprint across stages, details and navigation',async({page})=>{
 await page.goto('/?mock');await expect(page.locator('.composer-shell')).toBeVisible();
 await page.evaluate(()=>window.offlineBridge.event.emit(JSON.stringify({type:'chatChanged',id:'image-fixture',messages:[{id:'image-job',role:'assistant',taskType:'image',status:'Preparing the local image engine',targetDimensions:'3840 × 2160',prompt:'Synthetic fixture',imageProgress:{state:'PREPARING'}}]})));
 const surface=page.locator('.generation-surface');await expect(surface).toBeVisible();
 const before=await surface.boundingBox();expect(before.width).toBeGreaterThan(470);
 await page.locator('.generation-details summary').click();const after=await surface.boundingBox();expect(Math.abs(before.width-after.width)).toBeLessThan(2);expect(Math.abs(before.height-after.height)).toBeLessThan(2);
 await page.getByRole('navigation',{name:'Primary destinations'}).getByRole('button',{name:'Models',exact:true}).click();
 await page.getByRole('navigation',{name:'Primary destinations'}).getByRole('button',{name:'Chats',exact:true}).click();
 expect(Math.abs(before.width-(await surface.boundingBox()).width)).toBeLessThan(2);
});

test('model read failure is actionable and never masquerades as an empty registry',async({page})=>{
 await page.route('**/src/mockAdapter.js',async route=>{const response=await route.fetch();await route.fulfill({response,body:(await response.text()).replace('workspaceRequest: (action, raw, cb) => {','workspaceRequest: (action, raw, cb) => { if(window.__registryReadError){cb(JSON.stringify({ok:false,error:"Fixture read failed"}));return;}')});});
 await page.goto('/?mock');await expect(page.locator('.composer-shell')).toBeVisible();
 await page.evaluate(()=>{window.__registryReadError=true;window.offlineBridge.event.emit(JSON.stringify({type:'busy',value:true,status:'Generating image'}));});
 await page.getByRole('navigation',{name:'Primary destinations'}).getByRole('button',{name:'Models',exact:true}).click();
 await expect(page.getByRole('alert')).toContainText('Fixture read failed');
 await expect(page.getByText('No model references imported',{exact:true})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Refresh',exact:true})).toBeEnabled();
});

test('Live Voice control labels fit inside their clickable buttons',async({page})=>{
 await page.goto('/?mock');await expect(page.locator('.composer-shell')).toBeVisible();
 await expect(page.locator('.assistant-message')).toBeVisible();
 await page.evaluate(()=>new Promise(resolve=>window.offlineBridge.currentChat(chatId=>{window.offlineBridge.event.emit(JSON.stringify({type:'liveVoiceSession',chatId,sessionId:'layout-fixture',generation:1,revision:1,state:'paused',active:true,muted:true,prepared:true,captureReady:false,captureRequested:false}));resolve();})));
 const controls=page.locator('.voice-session-controls');await expect(controls).toBeVisible();
 for(const button of await controls.getByRole('button').all()){
  const outer=await button.boundingBox(),label=await button.locator('span').boundingBox();
  expect(label.y).toBeGreaterThanOrEqual(outer.y);expect(label.y+label.height).toBeLessThanOrEqual(outer.y+outer.height);
  expect(label.x+label.width).toBeLessThanOrEqual(outer.x+outer.width);
 }
});
