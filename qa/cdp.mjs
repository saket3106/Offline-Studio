// Drive the real Offline Studio UI through QtWebEngine's DevTools endpoint.
// Launch the app with QTWEBENGINE_REMOTE_DEBUGGING=9333 (loopback only), then:
//   node qa/cdp.mjs eval "<js expression>"        -> prints JSON result
//   node qa/cdp.mjs evalfile <file.js>             -> runs an async script body, prints JSON
//   node qa/cdp.mjs shot <out.png>                 -> page screenshot (web content)
// Read-only by default; scripts may click real controls, exactly like a user.
import { writeFileSync, readFileSync } from "node:fs";

const port = process.env.CDP_PORT || "9333";
const [, , cmd, arg] = process.argv;
const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
const page = targets.find((t) => t.type === "page" && /index\.html/.test(t.url)) || targets.find((t) => t.type === "page");
if (!page) throw new Error("No Offline Studio page target");
const ws = new WebSocket(page.webSocketDebuggerUrl);
let id = 0; const waiting = new Map();
ws.onmessage = (event) => { const msg = JSON.parse(event.data); if (msg.id && waiting.has(msg.id)) { waiting.get(msg.id)(msg); waiting.delete(msg.id); } };
await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
const send = (method, params = {}) => new Promise((resolve) => { const n = ++id; waiting.set(n, resolve); ws.send(JSON.stringify({ id: n, method, params })); });

async function evaluate(expression) {
  const res = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true, timeout: 600000 });
  if (res.result?.exceptionDetails) throw new Error(JSON.stringify(res.result.exceptionDetails).slice(0, 2000));
  return res.result?.result?.value;
}

try {
  if (cmd === "eval") console.log(JSON.stringify(await evaluate(arg), null, 2));
  else if (cmd === "evalfile") {
    // Arguments: CDP_ARGS env var (JSON) avoids shell quoting problems; argv[4] also accepted.
    const args = process.env.CDP_ARGS || process.argv[4] || "{}";
    JSON.parse(args);
    console.log(JSON.stringify(await evaluate(`(async()=>{const ARGS=${args};${readFileSync(arg, "utf8")}})()`), null, 2));
  }
  else if (cmd === "shot") {
    const res = await send("Page.captureScreenshot", { format: "png" });
    writeFileSync(arg, Buffer.from(res.result.data, "base64")); console.log(arg);
  } else throw new Error("usage: eval <js> | evalfile <file> | shot <out.png>");
} finally { ws.close(); }
