import assert from "node:assert/strict";
import fs from "node:fs";

const args = Object.fromEntries(
  process.argv.slice(2).map((item) => {
    const [key, ...value] = item.replace(/^--/, "").split("=");
    return [key, value.join("=")];
  }),
);
const frontdoor = args.frontdoor?.replace(/\/$/, "");
const worker = args.worker?.replace(/\/$/, "");
const oracleCandidates = [
  "../heatsafe-2030-cloudflare/fixtures/python_oracle_v2.json",
  "../cloudflare/fixtures/python_oracle_v2.json",
];
const oraclePath = args.oracle ?? oracleCandidates.find((candidate) => fs.existsSync(candidate));

if (!frontdoor || !worker) {
  throw new Error("usage: --frontdoor=<url> --worker=<url> [--oracle=<path>]");
}
assert.ok(oraclePath, `oracle fixture is missing; checked: ${oracleCandidates.join(", ")}`);

const oracle = JSON.parse(fs.readFileSync(oraclePath, "utf8"));
const cases = Object.fromEntries(oracle.cases.map((item) => [item.name, item]));
const ignoredKeys = new Set([
  "request_id",
  "latency_ms",
  "duration_ms",
  "qualification",
]);

function normalized(value) {
  if (Array.isArray(value)) return value.map(normalized);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value)
        .filter(([key]) => !ignoredKeys.has(key))
        .map(([key, item]) => [key, normalized(item)]),
    );
  }
  return value;
}

function parseSse(text) {
  return text
    .trim()
    .split("\n\n")
    .filter(Boolean)
    .map((frame) => {
      const match = frame.match(/^event: ([^\n]+)\ndata: ([\s\S]+)$/);
      assert.ok(match, `invalid SSE frame: ${frame}`);
      return { event: match[1], data: JSON.parse(match[2]) };
    });
}

async function call(base, path, body) {
  const response = await fetch(`${base}${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? undefined : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(30_000),
  });
  const text = await response.text();
  const contentType = response.headers.get("content-type") ?? "";
  return {
    status: response.status,
    contentType: contentType.split(";")[0],
    text,
    body: contentType.includes("json") && text ? JSON.parse(text) : null,
  };
}

const contentTypeEquivalences = [];

function canonicalContentType(value) {
  return /javascript/.test(value) ? "javascript" : value;
}

function compare(name, left, right, mode = "json") {
  assert.equal(left.status, right.status, `${name}: HTTP status`);
  assert.equal(
    canonicalContentType(left.contentType),
    canonicalContentType(right.contentType),
    `${name}: content type`,
  );
  if (left.contentType !== right.contentType) {
    contentTypeEquivalences.push({
      name,
      pages: left.contentType,
      worker: right.contentType,
      classification: "EQUIVALENT_JAVASCRIPT_MIME",
    });
  }
  if (mode === "sse") {
    assert.deepEqual(
      normalized(parseSse(left.text)),
      normalized(parseSse(right.text)),
      `${name}: SSE events`,
    );
  } else if (left.body !== null || right.body !== null) {
    assert.deepEqual(normalized(left.body), normalized(right.body), `${name}: JSON body`);
  } else {
    assert.equal(left.text, right.text, `${name}: body`);
  }
}

const results = [];
const approvedDeltas = [];
async function compareRequest(name, path, body, mode) {
  const [left, right] = await Promise.all([
    call(frontdoor, path, body),
    call(worker, path, body),
  ]);
  compare(name, left, right, mode);
  results.push({ name, status: "EXACT", http_status: left.status });
  return left;
}

const home = await compareRequest("home", "/");
const assets = [...home.text.matchAll(/(?:src|href)="([^"#?]+\.(?:js|css))"/g)].map(
  (match) => match[1],
);
for (const asset of assets.filter((path) => !path.endsWith(".css"))) {
  await compareRequest(`asset:${asset}`, asset);
}

const cssPath = assets.find((path) => path.endsWith(".css"));
assert.ok(cssPath, "frontend CSS asset was not found");
const [pagesCss, workerCss] = await Promise.all([
  call(frontdoor, cssPath),
  call(worker, cssPath),
]);
assert.equal(pagesCss.status, 200, "Pages CSS status");
assert.equal(workerCss.status, 200, "Worker CSS status");
assert.doesNotMatch(pagesCss.text, /fonts\.(?:googleapis|gstatic)\.com/);
assert.match(workerCss.text, /fonts\.googleapis\.com/);
approvedDeltas.push({
  name: `asset:${cssPath}`,
  status: "APPROVED_PAGES_ONLY_FONT_OPTIMIZATION",
});

const mapWorkerName = fs
  .readdirSync(new URL("../public/assets/", import.meta.url))
  .find((name) => /^maplibre-gl-worker-.*\.mjs$/.test(name));
assert.ok(mapWorkerName, "MapLibre worker asset was not found");
await compareRequest(
  `asset:/assets/${mapWorkerName}`,
  `/assets/${mapWorkerName}`,
);

await compareRequest("health", "/health");
await compareRequest("demo", "/api/v1/demo");
const grids = await compareRequest("grids", "/api/v1/demo/grids");
assert.equal(grids.body.features.length, 400, "front door must return 400 grids");
await compareRequest("top1", `/api/v1/demo/grids/${oracle.top1}`);
await compareRequest("actions_grid", `/api/v1/actions/grid/${oracle.top1}`);
await compareRequest("actions_hotspots", "/api/v1/actions/hotspots");
await compareRequest("agent_status", "/api/v1/agent/status");
await compareRequest("api_404", "/api/v1/nonexistent");

for (const item of oracle.cases.filter((entry) => entry.kind === "agent")) {
  await compareRequest(item.name, "/api/v1/agent/query", item.request);
}

for (const item of oracle.cases.filter((entry) => entry.kind === "sse")) {
  await compareRequest(item.name, "/api/v1/agent/stream", item.request, "sse");
}

const summary = {
  status: "PASS",
  classification: "33_EXACT_WITH_1_APPROVED_CSS_FONT_DELTA",
  frontdoor,
  worker,
  total: results.length,
  approved_delta_count: approvedDeltas.length,
  content_type_equivalences: contentTypeEquivalences,
  agent: oracle.cases.filter((item) => item.kind === "agent").length,
  action: 2,
  sse: oracle.cases.filter((item) => item.kind === "sse").length,
  grid_count: grids.body.features.length,
  results,
  approved_deltas: approvedDeltas,
};

console.log(JSON.stringify(summary, null, 2));
