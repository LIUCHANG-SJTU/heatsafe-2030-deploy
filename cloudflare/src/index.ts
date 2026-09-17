import { EvidenceLedger } from "./contracts";
import { gridActionsTool, hotspotActionsTool } from "./actions";
import { answerAgent, status } from "./agent";
import { artifact, grids, byId, executeTool } from "./tools";
import { validateAnswer } from "./validator";

const JSON_HEADERS={"content-type":"application/json; charset=utf-8"};
const json=(data:any,statusCode=200)=>new Response(JSON.stringify(data),{status:statusCode,headers:JSON_HEADERS});
const compactKeys=["grid_id","analysis_status","analysis_reasons","ranking_eligible","landsat_quality_flag","sentinel_quality_flag","risk_score","risk_percentile_within_aoi","hazard_score","exposure_score","vulnerability_score","adaptive_capacity_score","population_total","lst_median_c","green_fraction_land","water_fraction_grid","primary_driver"];

function sseEvent(event:string,data:any){return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;}
function streamAgent(body:any):Response{
  const requestId=crypto.randomUUID(),locale=body?.context?.locale??"zh-CN",frames=[sseEvent("request",{request_id:requestId}),sseEvent("status",{message:locale==="en"?"Reading HeatSafe data…":"正在读取 HeatSafe 数据…"})];
  try{
    const result=answerAgent(body);result.request_id=requestId;
    for(const trace of result.tool_trace)frames.push(sseEvent("tool",trace));
    if(result.evidence.length)frames.push(sseEvent("evidence",{items:result.evidence}));
    frames.push(sseEvent("status",{message:locale==="en"?"Validating evidence…":"正在验证数据依据…"}));
    const words=result.answer.split(" ");words.forEach((word:string,index:number)=>frames.push(sseEvent("token",{text:word+(index<words.length-1?" ":"")})));
    frames.push(sseEvent("done",result));
  }catch{
    frames.push(sseEvent("error",{request_id:requestId,code:"AGENT_REQUEST_FAILED",message:locale==="en"?"HeatSafe Agent request failed.":"HeatSafe Agent 请求失败。"}));
  }
  return new Response(frames.join(""),{headers:{"content-type":"text/event-stream","cache-control":"no-cache","x-accel-buffering":"no"}});
}

async function fetchHandler(request:Request):Promise<Response>{
  const url=new URL(request.url),path=url.pathname;
  try{
    if(path==="/health")return json({status:"ok",service:"heatsafe-2030",version:"1.0.0",data_mode:"REAL",default_analysis_mode:"REAL"});
    if(path==="/api/v1/demo")return json(Object.fromEntries(Object.entries(artifact).filter(([key])=>key!=="grids")));
    if(path==="/api/v1/demo/grids")return json({type:"FeatureCollection",name:artifact.demo_id,features:grids.map(grid=>({type:"Feature",id:grid.grid_id,geometry:grid.geometry,properties:{...Object.fromEntries(compactKeys.map(key=>[key,grid[key]??null])),H:grid.hazard_score,E:grid.exposure_score,V:grid.vulnerability_score,A:grid.adaptive_capacity_score}}))});
    if(path.startsWith("/api/v1/demo/grids/")){const id=decodeURIComponent(path.split("/").pop()!),grid=byId.get(id);if(!grid)return json({detail:"demo grid not found"},404);return json({...grid,methods:artifact.methods,quality:{lst_valid_fraction:grid.lst_valid_fraction,sentinel_valid_fraction:grid.sentinel_valid_fraction,analysis_status:grid.analysis_status},provenance:{source_ids:grid.source_ids,manifest:"data/provenance/demo_v1/manifest.json"},temporal_context:artifact.temporal_context});}
    if(path==="/api/v1/actions/hotspots"){const result=new EvidenceLedger().append(hotspotActionsTool(Number(url.searchParams.get("limit")??5)));return json(result.data);}
    if(path.startsWith("/api/v1/actions/grid/")){const id=decodeURIComponent(path.split("/").pop()!);if(!byId.has(id))return json({detail:"demo grid not found"},404);const result=new EvidenceLedger().append(gridActionsTool(id));return json(result.data);}
    if(path==="/api/v1/agent/status")return json(status());
    if(path==="/api/v1/agent/query"&&request.method==="POST"){try{return json(answerAgent(await request.json()));}catch(error:any){return json({detail:error.message},422);}}
    if(path==="/api/v1/agent/stream"&&request.method==="POST")return streamAgent(await request.json());
    if(path.startsWith("/api/"))return json({detail:"Not Found"},404);
    return new Response("Not Found",{status:404});
  }catch(error:any){return json({detail:error.message??"request failed"},422);}
}

export const __test={executeTool:(name:string,payload:any)=>new EvidenceLedger().append(name==="recommend_actions"?(payload.scope==="hotspots"?hotspotActionsTool(payload.limit??5):gridActionsTool(payload.grid_id,payload.limit??3)):executeTool(name,payload)),validateAnswer,answerAgent};
export default {fetch:fetchHandler};
