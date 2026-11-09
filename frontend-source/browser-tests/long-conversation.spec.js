import {test,expect} from '@playwright/test';

test('long conversation keeps source targets, manual scroll and copy-code',async({page,context},testInfo)=>{
 await context.grantPermissions(['clipboard-read','clipboard-write']);
 await page.addInitScript(()=>{
  let native;
  Object.defineProperty(window,'offlineBridge',{configurable:true,get:()=>native,set:bridge=>{
   native=bridge;
   // Seed the DEV fixture before the facade caches its first loadChat call.
   bridge.loadChat=(_id,cb)=>cb(JSON.stringify(window.longFixture||[{id:2,role:'assistant',content:'Initial authored fixture'}]));
  }});
 });
 await page.goto('/?mock');await expect(page.locator('.assistant-message')).toBeVisible();
 await page.evaluate(()=>{
  window.longFixture=Array.from({length:400},(_,i)=>({id:1000+i,sourceMessageId:1000+i,role:i%2?'assistant':'user',content:i%2?`Response ${i}\n\n${'Local authored fixture paragraph. '.repeat(10)}\n\n\`\`\`python\nprint(${i})\n\`\`\``:`Request ${i}`}));
  window.offlineBridge.event.emit(JSON.stringify({type:'chatChanged',id:'long-fixture',messages:window.longFixture}));
 });
 await expect(page.locator('.message-row')).toHaveCount(400);
 await expect(page.locator('.message-row').first()).toHaveCSS('content-visibility','auto');
 await expect(page.locator('.message-row').last()).toHaveCSS('content-visibility','visible');
 const viewport=page.locator('.conversation-viewport');
 await viewport.evaluate(e=>{e.scrollTop=0;e.dispatchEvent(new Event('scroll'));});
 await page.evaluate(()=>window.offlineBridge.event.emit(JSON.stringify({type:'append',chatId:'long-fixture',id:1399,text:' STREAMED-SENTINEL'})));
 await expect(page.locator('.message-row').last()).toContainText('STREAMED-SENTINEL');
 expect(await viewport.evaluate(e=>e.scrollTop)).toBeLessThan(5);
 await page.evaluate(()=>{
  window.offlineBridge.event.emit(JSON.stringify({type:'navigateChat',targetChatId:'long-fixture',messageId:1101}));
 });
 const target=page.locator('[data-source-message="1101"]');
 await expect(target).toBeInViewport({timeout:5000});
 await target.getByRole('button',{name:'Copy code',exact:true}).click();
 await expect.poll(()=>page.evaluate(()=>navigator.clipboard.readText())).toContain('print(101)');
 await page.screenshot({path:testInfo.outputPath('long-chat.png')});
 await page.getByRole('textbox',{name:'Message input'}).focus();
 await expect(page.getByRole('textbox',{name:'Message input'})).toBeFocused();
});

test('long conversation retains streaming Stop and scroll-to-bottom',async({page})=>{
 await page.goto('/?mock');await expect(page.locator('.assistant-message')).toBeVisible();
 await page.evaluate(()=>window.offlineBridge.event.emit(JSON.stringify({type:'chatChanged',id:'fixture-0',messages:Array.from({length:200},(_,i)=>({id:2000+i,role:i%2?'assistant':'user',content:'Authored long conversation '+i}))})));
 await expect(page.locator('.message-row')).toHaveCount(200);
 await page.locator('.conversation-viewport').evaluate(e=>{e.scrollTop=0;e.dispatchEvent(new Event('scroll'));});
 await page.getByRole('button',{name:'Scroll to bottom',exact:true}).click();
 await expect.poll(()=>page.locator('.conversation-viewport').evaluate(e=>e.scrollHeight-e.scrollTop-e.clientHeight)).toBeLessThan(5);
 await page.getByRole('textbox',{name:'Message input'}).fill('Synthetic streaming continuation');
 await page.getByRole('button',{name:'Send message',exact:true}).click();
 await page.getByRole('button',{name:'Stop generation'}).click();
 await expect(page.getByRole('button',{name:'Send message',exact:true})).toBeVisible();
 await expect(page.locator('.message-row').last()).toHaveCSS('content-visibility','visible');
});
