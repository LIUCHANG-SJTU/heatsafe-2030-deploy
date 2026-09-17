import { test } from 'node:test';
import assert from 'node:assert/strict';
import worker from '../dist-worker.mjs';

async function call(path, init) {
  const response = await worker.fetch(new Request(`https://local.test${path}`, init));
  const text = await response.text();
  return { response, body: text ? JSON.parse(text) : null };
}

test('public read-only API exposes frozen demo', async () => {
  const summary = await call('/api/v1/demo');
  assert.equal(summary.response.status, 200);
  assert.equal(summary.body.summary.total_grid_count, 400);
  assert.equal(summary.body.summary.analyzable_land_grid_count, 315);
  const grids = await call('/api/v1/demo/grids');
  assert.equal(grids.body.features.length, 400);
});

test('agent is provider-disabled and grounded', async () => {
  const status = await call('/api/v1/agent/status');
  assert.equal(status.body.enabled, false);
  assert.deepEqual(status.body.tools, ['get_demo_summary','inspect_grid','list_hotspots','compare_grids','query_grids','explain_risk','get_methodology','recommend_actions']);
  const answer = await call('/api/v1/agent/query', {method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({messages:[{role:'user',content:'What is the risk?'}],context:{selected_grid_id:'M4B-R-5EEC8B7710-G-R16-C13',locale:'en'}})});
  assert.equal(answer.response.status, 200);
  assert.equal(answer.body.validation.status, 'PASS');
  assert.match(answer.body.answer, /relative risk/);
  assert.ok(answer.body.evidence.every((e) => /^E\d+$/.test(e.evidence_id)));
});

test('SSE uses validated event envelope', async () => {
  const response = await worker.fetch(new Request('https://local.test/api/v1/agent/stream',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({messages:[{role:'user',content:'请查看这个格网'}],context:{selected_grid_id:'M4B-R-5EEC8B7710-G-R16-C13',locale:'zh-CN'}})}));
  const body = await response.text();
  assert.equal(response.status, 200);
  for (const event of ['request','status','tool','evidence','token','done']) assert.match(body, new RegExp(`event: ${event}`));
});

test('unknown API path is JSON 404', async () => {
  const x = await call('/api/v1/unknown');
  assert.equal(x.response.status, 404);
  assert.equal(x.body.detail, 'Not Found');
});
