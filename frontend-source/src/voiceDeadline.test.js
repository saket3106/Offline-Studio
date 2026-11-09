import test from 'node:test';
import assert from 'node:assert/strict';
import {voiceDeadline} from './voiceCapture.js';
test('voice setup deadlines release a microphone that resolves too late',async()=>{
 let resolve,disposed=false;const operation=new Promise(r=>resolve=r);
 await assert.rejects(voiceDeadline(operation,5,'permission timeout',()=>disposed=true),/permission timeout/);
 resolve({});await new Promise(r=>setTimeout(r,0));assert.equal(disposed,true);
 assert.equal(await voiceDeadline(Promise.resolve('ready'),50,'timeout'),'ready');
});
