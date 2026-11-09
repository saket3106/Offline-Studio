import { readFileSync, writeFileSync } from "node:fs";
const css = readFileSync("src/tokens.css", "utf8");
const block = (selector) => {
  const start = css.indexOf(selector);
  if (start < 0) throw Error("Missing palette " + selector);
  return Object.fromEntries(
    [
      ...css
        .slice(start, css.indexOf("}", start))
        .matchAll(/(--[\w-]+):\s*([^;]+);/g),
    ].map((m) => [m[1], m[2].trim()]),
  );
};
const dark = block(":root {"),
  light = { ...dark, ...block(':root[data-theme="light"]') },
  contrast = { ...dark, ...block(':root[data-contrast="true"]') };
function luminance(hex) {
  let h = hex.replace("#", "");
  if (h.length === 3) h = [...h].map((c) => c + c).join("");
  const rgb = [0, 2, 4]
    .map((i) => parseInt(h.slice(i, i + 2), 16) / 255)
    .map((v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
}
function ratio(a, b) {
  const x = luminance(a),
    y = luminance(b);
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
}
const results = [];
for (const [name, palette] of Object.entries({ dark, light, contrast })) {
  for (const text of ["--text-primary", "--text-secondary", "--text-muted"])
    for (const background of [
      "--bg-canvas",
      "--bg-sidebar",
      "--bg-surface-1",
      "--bg-surface-2",
    ])
      results.push({
        theme: name,
        text,
        background,
        ratio: ratio(palette[text], palette[background]),
        minimum: 4.5,
      });
  for (const background of ["--bg-canvas", "--bg-surface-1"])
    results.push({
      theme: name,
      text: "--border-control",
      background,
      ratio: ratio(palette["--border-control"], palette[background]),
      minimum: 3,
    });
}
const failed = results.filter((r) => r.ratio < r.minimum);
writeFileSync(
  "../docs/ui-contrast.json",
  JSON.stringify(
    {
      scope:
        "Semantic text and control-border token pairs; decorative hairlines exempt, actual rendered states also checked by axe",
      checks: results,
      failed,
    },
    null,
    2,
  ),
);
console.log(
  `${results.length - failed.length}/${results.length} contrast checks passed`,
);
if (failed.length) {
  console.error(failed);
  process.exit(1);
}
