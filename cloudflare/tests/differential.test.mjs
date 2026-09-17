import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import worker, { __test } from '../dist-worker.mjs';

const oracle=JSON.parse(fs.readFileSync(new URL('../fixtures/python_oracle_v2.json',import.meta.url)));
const cases=Object.fromEntries(oracle.cases.map(item=>[item.name,item]));

function normalized(value){
  if(Array.isArray(value))return value.map(normalized);
  if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).filter(([key])=>!['request_id','latency_ms','duration_ms','qualification'].includes(key)).map(([key,item])=>[key,normalized(item)]));
  return value;
}

async function call(path,body){const response=await worker.fetch(new Request(`https://local.test${path}`,body===undefined?undefined:{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)}));const text=await response.text();return {status:response.status,type:response.headers.get('content-type')||'',text,body:response.headers.get('content-type')?.includes('json')?JSON.parse(text):null};}
function parseSse(text){return text.trim().split('\n\n').map(frame=>{const match=frame.match(/^event: ([^\n]+)\ndata: ([\s\S]+)$/);assert.ok(match,`invalid SSE frame: ${frame}`);return {event:match[1],data:JSON.parse(match[2])};});}

test('all nine public tool fixtures are exact',()=>{
  for(const expected of oracle.cases.filter(item=>item.kind==='tool'))assert.deepEqual(__test.executeTool(expected.tool,expected.request),expected.result,expected.name);
});

test('all nineteen provider-none Agent fixtures are exact after nondeterministic fields are removed',()=>{
  for(const expected of oracle.cases.filter(item=>item.kind==='agent')){
    if(expected.error){assert.throws(()=>__test.answerAgent(expected.request),new RegExp(expected.error.message),expected.name);continue;}
    assert.deepEqual(normalized(__test.answerAgent(expected.request)),expected.response,expected.name);
  }
});

test('both Action API fixtures are exact',async()=>{
  assert.deepEqual((await call(`/api/v1/actions/grid/${oracle.top1}`)).body,cases.api_actions_grid.response);
  assert.deepEqual((await call('/api/v1/actions/hotspots')).body,cases.api_actions_hotspots.response);
});

test('three SSE fixtures preserve event order, tokens, done and error behavior',async()=>{
  for(const expected of oracle.cases.filter(item=>item.kind==='sse')){
    const actual=await call('/api/v1/agent/stream',expected.request);
    assert.equal(actual.status,expected.http_status,expected.name);
    assert.match(actual.type,/text\/event-stream/,expected.name);
    assert.deepEqual(normalized(parseSse(actual.text)),normalized(expected.events),expected.name);
    const reconstructed=parseSse(actual.text).filter(item=>item.event==='token').map(item=>item.data.text).join('');
    assert.equal(reconstructed,expected.reconstructed_text??'',expected.name);
  }
});

test('HTTP API and static routing contract',async()=>{
  assert.equal((await call('/health')).status,200);
  const demo=await call('/api/v1/demo');assert.equal(demo.status,200);assert.equal(demo.body.summary.total_grid_count,400);
  const grids=await call('/api/v1/demo/grids');assert.equal(grids.status,200);assert.equal(grids.body.features.length,400);
  assert.equal((await call(`/api/v1/demo/grids/${oracle.top1}`)).status,200);
  const bad=await call('/api/v1/nonexistent');assert.equal(bad.status,404);assert.match(bad.type,/application\/json/);assert.equal(bad.body.detail,'Not Found');
  const invalid=await call('/api/v1/agent/query',cases.agent_invalid_grid.request);assert.equal(invalid.status,422);assert.equal(invalid.body.detail,cases.agent_invalid_grid.error.message);
});

test('canonical validator fixtures are exact',()=>{
  const evidence=[{evidence_id:'E1',metric:'risk_score',label:'Risk score',value:90.18907524978329,unit:'/100',grid_id:oracle.top1,source_component:'RISK_MODEL',source_ref:'heatsafe_demo_v1_2026',method:null,data_mode:'REAL',qa_status:null}];
  for(const item of oracle.validator_cases)assert.deepEqual(__test.validateAnswer(item.answer,evidence),item.expected,item.name);
});
