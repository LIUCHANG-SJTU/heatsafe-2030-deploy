import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { onRequest } from "../functions/[[path]].ts";

test("passes the original request to the HEATSAFE service binding", async () => {
  const request = new Request(
    "https://heatsafe-2030.pages.dev/api/v1/agent/query?lang=zh",
    {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-frontdoor-test": "preserved",
      },
      body: JSON.stringify({ message: "test", selected_grid_id: "grid-1" }),
    },
  );
  let received;
  const expected = Response.json({ status: "PASS" });

  const response = await onRequest({
    request,
    env: {
      HEATSAFE: {
        fetch(boundRequest) {
          received = boundRequest;
          return Promise.resolve(expected);
        },
      },
    },
  });

  assert.equal(received, request);
  assert.equal(response, expected);
  assert.equal(received.method, "POST");
  assert.equal(received.url, request.url);
  assert.equal(received.headers.get("x-frontdoor-test"), "preserved");
  assert.deepEqual(await received.json(), {
    message: "test",
    selected_grid_id: "grid-1",
  });
});

test("returns an SSE response without reading or buffering its body", async () => {
  const encoder = new TextEncoder();
  let startCalled = false;
  const stream = new ReadableStream({
    start(controller) {
      startCalled = true;
      controller.enqueue(encoder.encode("event: request\ndata: {}\n\n"));
      controller.enqueue(encoder.encode("event: done\ndata: {}\n\n"));
      controller.close();
    },
  });
  const expected = new Response(stream, {
    headers: { "content-type": "text/event-stream" },
  });

  const response = await onRequest({
    request: new Request("https://heatsafe-2030.pages.dev/api/v1/agent/stream", {
      method: "POST",
      body: "{}",
    }),
    env: { HEATSAFE: { fetch: async () => expected } },
  });

  assert.equal(response, expected);
  assert.equal(response.headers.get("content-type"), "text/event-stream");
  assert.equal(startCalled, true);
  assert.match(await response.text(), /event: request/);
  assert.match(await response.text().catch(() => "already consumed"), /already consumed/);
});

test("forwards only configured dynamic paths through the binding", async () => {
  const routes = JSON.parse(
    fs.readFileSync(new URL("../public/_routes.json", import.meta.url), "utf8"),
  );
  assert.deepEqual(routes, {
    version: 1,
    include: ["/health", "/api/*"],
    exclude: [],
  });

  for (const path of ["/health", "/api/v1/demo"]) {
    const request = new Request(`https://heatsafe-2030.pages.dev${path}`);
    let received;
    const response = await onRequest({
      request,
      env: {
        HEATSAFE: {
          fetch(boundRequest) {
            received = boundRequest;
            return Promise.resolve(new Response(path));
          },
        },
      },
    });

    assert.equal(received, request);
    assert.equal(await response.text(), path);
  }
});

test("contains the accepted frontend and local MapLibre assets without remote fonts", () => {
  const publicUrl = new URL("../public/", import.meta.url);
  const assetsUrl = new URL("assets/", publicUrl);
  const assetNames = fs.readdirSync(assetsUrl);
  const cssName = assetNames.find((name) => /^index-.*\.css$/.test(name));
  const workerName = assetNames.find((name) => /^maplibre-gl-worker-.*\.mjs$/.test(name));

  assert.ok(fs.existsSync(new URL("index.html", publicUrl)));
  assert.ok(cssName);
  assert.ok(workerName);
  assert.ok(fs.existsSync(new URL("maplibre-gl-shared.mjs", assetsUrl)));
  const css = fs.readFileSync(new URL(cssName, assetsUrl), "utf8");
  assert.doesNotMatch(css, /fonts\.(?:googleapis|gstatic)\.com/);
});
