import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const css=readFileSync(new URL('./premium.css',import.meta.url),'utf8');
const app=readFileSync(new URL('./main.jsx',import.meta.url),'utf8');
test('Premium stylesheet is included after prior design layers',()=>{
  assert.match(app,/import "\.\/upgrade\.css";\s*import "\.\/premium\.css";/);
  assert.match(app,/className="chat-editorial-subtitle"/);
});
test('Premium dark and light palettes use explicit offline-friendly tokens',()=>{
  assert.match(css,/:root\[data-theme="dark"\]/);
  assert.match(css,/:root\[data-theme="light"\]/);
  assert.match(css,/--bg-canvas:\s*#0c0c0d/);
  assert.match(css,/--bg-canvas:\s*#fcfcfb/);
  assert.doesNotMatch(css,/@import\s+url\(https?:/i);
  assert.doesNotMatch(css,/fonts\.googleapis\.com/i);
});
test('Premium layouts retain the existing live Qt and React handlers',()=>{
  for (const selector of ['.chat-greeting','.composer-shell','.sidebar','.context-inspector','.model-manager-item','.creation-workspace','.library-card','.settings-dialog','.runtime-statusbar'])
    assert.ok(css.includes(selector),`missing design target ${selector}`);
  for (const handler of ['<ModelSelector','<Composer','<ContextInspector','<HeaderTelemetry'])
    assert.ok(app.includes(handler),`missing live UI component ${handler}`);
});
