import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

test("production assets include the MapLibre module worker", () => {
  const html = fs.readFileSync(new URL("../frontend/dist/index.html", import.meta.url), "utf8");
  const scriptPath = html.match(/src="(\/assets\/[^"]+\.js)"/)?.[1];
  assert.ok(scriptPath, "frontend entry script is missing");
  const script = fs.readFileSync(new URL(`../frontend/dist${scriptPath}`, import.meta.url), "utf8");
  const workerPath = script.match(/assets\/maplibre-gl-worker-[A-Za-z0-9_-]+\.mjs/)?.[0];
  assert.ok(workerPath, "MapLibre worker URL was not emitted into the frontend bundle");
  const workerUrl = new URL(`../frontend/dist/${workerPath}`, import.meta.url);
  assert.ok(fs.statSync(workerUrl).size > 0, "MapLibre worker asset is empty");
  const sharedUrl = new URL("../frontend/dist/assets/maplibre-gl-shared.mjs", import.meta.url);
  assert.ok(fs.statSync(sharedUrl).size > 0, "MapLibre shared worker module is missing or empty");
  assert.match(fs.readFileSync(workerUrl, "utf8"), /from"\.\/maplibre-gl-shared\.mjs"/);
});
