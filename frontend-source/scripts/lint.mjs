// Bounded syntax/forbidden-interface lint using the already installed Babel parser.
// This is not represented as ESLint or Prettier acceptance.
import { createRequire } from "node:module";
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
const require = createRequire(import.meta.url);
const parser = require("../node_modules/.pnpm/node_modules/@babel/parser");
let count = 0;
function walk(node, file) {
  if (!node || typeof node !== "object") return;
  if (node.type === "JSXOpeningElement" && node.name?.name === "select")
    throw Error("Native select remains: " + file);
  for (const value of Object.values(node)) {
    if (Array.isArray(value)) value.forEach((n) => walk(n, file));
    else if (value && typeof value === "object") walk(value, file);
  }
}
for (const file of readdirSync("src").filter((f) => /\.(jsx|js)$/.test(f))) {
  const code = readFileSync(path.join("src", file), "utf8");
  walk(parser.parse(code, { sourceType: "module", plugins: ["jsx"] }), file);
  if (/fonts\.googleapis\.com|https:\/\/.*cdn\./.test(code))
    throw Error("Remote asset dependency: " + file);
  count++;
}
console.log(
  `PASS: ${count} source modules parsed; no native select or remote CDN/font dependency`,
);
