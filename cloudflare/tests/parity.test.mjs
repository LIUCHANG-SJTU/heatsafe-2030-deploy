import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import worker, { __test } from '../dist-worker.mjs';

const oracle = JSON.parse(fs.readFileSync(new URL('../fixtures/python_oracle_v2.json', import.meta.url)));
const cases = Object.fromEntries(oracle.cases.map((item) => [item.name, item]));

async function request(path, body) {
  const response = await worker.fetch(new Request(`https://local.test${path}`, body === undefined ? undefined : {
    method: 'POST', headers: {'content-type':'application/json'}, body: JSON.stringify(body),
  }));
  const text = await response.text();
  return { status: response.status, type: response.headers.get('content-type'), text, body: text && response.headers.get('content-type')?.includes('json') ? JSON.parse(text) : null };
}

test('intervention-effect request matches Python scope limitation', async () => {
  const expected = cases.agent_green_effect.response;
  const actual = await request('/api/v1/agent/query', cases.agent_green_effect.request);
  assert.equal(actual.body.answer_mode, expected.answer_mode);
  assert.equal(actual.body.answer, expected.answer);
});

test('constrained query routes to query_grids with matching evidence and map action', async () => {
  const expected = cases.agent_query_high_exposure_good_green.response;
  const actual = await request('/api/v1/agent/query', cases.agent_query_high_exposure_good_green.request);
  assert.deepEqual(actual.body.tool_trace.map(({duration_ms,...trace}) => trace), expected.tool_trace);
  assert.deepEqual(actual.body.map_actions, expected.map_actions);
  assert.deepEqual(actual.body.evidence, expected.evidence);
});

test('selected-grid action preserves supporting evidence, guidance and map action', async () => {
  const expectedApi = cases.api_actions_grid.response;
  const api = await request(`/api/v1/actions/grid/${oracle.top1}`);
  assert.deepEqual(api.body, expectedApi);
  const expectedAgent = cases.agent_actions.response;
  const agent = await request('/api/v1/agent/query', cases.agent_actions.request);
  assert.deepEqual(agent.body.map_actions, expectedAgent.map_actions);
  assert.deepEqual(agent.body.evidence, expectedAgent.evidence);
});

test('scope guard assigns request-local Evidence IDs', async () => {
  const expected = cases.agent_mortality.response;
  const actual = await request('/api/v1/agent/query', cases.agent_mortality.request);
  assert.deepEqual(actual.body.evidence, expected.evidence);
});

test('invalid-grid stream returns canonical SSE error event', async () => {
  const expected = cases.sse_invalid_grid;
  const actual = await request('/api/v1/agent/stream', expected.request);
  assert.equal(actual.status, 200);
  assert.match(actual.type || '', /text\/event-stream/);
  assert.match(actual.text, /event: error/);
  assert.match(actual.text, /AGENT_REQUEST_FAILED/);
});

test('validator is not an unconditional PASS placeholder', async () => {
  const evidence=[{evidence_id:'E1',metric:'risk_score',label:'Risk score',value:90.18907524978329,unit:'/100',grid_id:oracle.top1,source_component:'RISK_MODEL',source_ref:'heatsafe_demo_v1_2026',method:null,data_mode:'REAL',qa_status:null}];
  assert.deepEqual(__test.validateAnswer('相对风险为 90.2 [E1]。',evidence),oracle.validator_cases.find(x=>x.name==='validator_valid').expected);
  assert.deepEqual(__test.validateAnswer('相对风险为 90.2 [E2]。',evidence),oracle.validator_cases.find(x=>x.name==='validator_unknown_id').expected);
  assert.deepEqual(__test.validateAnswer('相对风险为 75.0 [E1]。',evidence),oracle.validator_cases.find(x=>x.name==='validator_unsupported_number').expected);
  assert.deepEqual(__test.validateAnswer('措施会让风险降低 20%。',evidence),oracle.validator_cases.find(x=>x.name==='validator_intervention').expected);
});
