import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const projectRoot = path.resolve(import.meta.dirname, "..");
const acceptedDistCandidates = [
  path.resolve(projectRoot, "../heatsafe-2030-cloudflare/frontend/dist"),
  path.resolve(projectRoot, "../cloudflare/frontend/dist"),
];
const acceptedDist = acceptedDistCandidates.find((candidate) =>
  fs.existsSync(path.join(candidate, "index.html")),
);
const publicDir = path.join(projectRoot, "public");

assert.ok(
  acceptedDist,
  `accepted frontend build is missing; checked: ${acceptedDistCandidates.join(", ")}`,
);
fs.mkdirSync(publicDir, { recursive: true });

for (const entry of fs.readdirSync(acceptedDist)) {
  fs.cpSync(path.join(acceptedDist, entry), path.join(publicDir, entry), {
    recursive: true,
    force: true,
  });
}

const cssFiles = fs
  .readdirSync(path.join(publicDir, "assets"))
  .filter((name) => /^index-.*\.css$/.test(name));
assert.equal(cssFiles.length, 1, "expected exactly one built application CSS file");

const cssPath = path.join(publicDir, "assets", cssFiles[0]);
const originalCss = fs.readFileSync(cssPath, "utf8");
const fontImport = /^@import"https:\/\/fonts\.googleapis\.com\/[^\"]+";/;
assert.match(originalCss, fontImport, "expected the measured Google Fonts import");

const sansStack =
  'system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",Arial,sans-serif';
const monoStack = '"SFMono-Regular",Consolas,"Liberation Mono",monospace';
const pagesCss = originalCss
  .replace(fontImport, "")
  .replaceAll("JetBrains Mono", monoStack)
  .replaceAll("Inter", sansStack);

assert.doesNotMatch(pagesCss, /fonts\.(?:googleapis|gstatic)\.com/);
fs.writeFileSync(cssPath, pagesCss);

for (const required of [
  "index.html",
  "assets/maplibre-gl-shared.mjs",
  "assets/maplibre-gl-worker-BJqgGX1f.mjs",
]) {
  assert.ok(fs.existsSync(path.join(publicDir, required)), `missing static asset: ${required}`);
}

console.log(
  JSON.stringify(
    {
      source: acceptedDist,
      destination: publicDir,
      css: cssFiles[0],
      external_font_dependency: "REMOVED_FROM_PAGES_COPY",
      source_runtime_modified: false,
    },
    null,
    2,
  ),
);
