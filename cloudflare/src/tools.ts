import artifactJson from "../data/processed/analysis/heatsafe_demo_v1_2026.json";
import { Evidence, Grid, ToolResult, fact, toolResult } from "./contracts";

export const artifact: any = artifactJson;
export const grids: Grid[] = artifact.grids;
export const byId = new Map<string, Grid>(grids.map((grid) => [String(grid.grid_id), grid]));
export const PUBLIC_TOOLS = ["get_demo_summary","inspect_grid","list_hotspots","compare_grids","query_grids","explain_risk","get_methodology","recommend_actions"];

const GRID_KEYS = ["grid_id","analysis_status","analysis_reasons","ranking_eligible","risk_score","risk_percentile_within_aoi","primary_driver","population_total","lst_median_c","ndvi_median_land","green_fraction_land","water_fraction_grid","child_share","elderly_share","hazard_score","exposure_score","vulnerability_score","adaptive_capacity_score","hazard_contribution_points","exposure_contribution_points","vulnerability_contribution_points","adaptive_deficit_contribution_points","landsat_quality_flag","sentinel_quality_flag","lst_valid_fraction","sentinel_valid_fraction"];

export function getGrid(id: string): Grid {
  const grid = byId.get(id);
  if (!grid) throw new Error(`unknown grid_id: ${id}`);
  return grid;
}

export function gridData(grid: Grid): Record<string, any> {
  return Object.fromEntries(GRID_KEYS.map((key) => [key, grid[key] ?? null]));
}

export function percentile(field: string, percentileValue: number): number {
  const values = grids.filter((grid) => grid.analysis_status === "ANALYZABLE_LAND" && typeof grid[field] === "number").map((grid) => Number(grid[field])).sort((a,b) => a-b);
  const position = (values.length - 1) * percentileValue;
  const lower = Math.floor(position), upper = Math.min(lower + 1, values.length - 1);
  return values[lower] + (values[upper] - values[lower]) * (position - lower);
}

export function summaryTool(): ToolResult {
  const s = artifact.summary;
  return toolResult("get_demo_summary", {
    demo_id: artifact.demo_id, event: artifact.aoi.event, aoi: artifact.aoi, risk_scope: artifact.risk_scope,
    data_mode: artifact.data_mode, model_status: artifact.model_status, qa_contract_version: artifact.qa_contract_version,
    summary: artifact.summary, methods: artifact.methods, weights: artifact.weights,
  }, [
    fact("total_grid_count", "Total grids", s.total_grid_count, {unit:"grids"}),
    fact("analyzable_land_grid_count", "Analyzable land", s.analyzable_land_grid_count, {unit:"grids"}),
    fact("water_excluded_grid_count", "Water excluded", s.water_excluded_grid_count, {unit:"grids"}),
    fact("total_population_est", "Total population", s.total_population_est, {source_component:"WORLDPOP",unit:"people"}),
    fact("temporal_severity_score", "Temporal severity", artifact.temporal_context.temporal_severity_score, {source_component:"ERA5_LAND"}),
    fact("risk_scope", "Risk scope", artifact.risk_scope, {source_component:"RISK_MODEL"}),
    fact("data_mode", "Data mode", artifact.data_mode),
    fact("model_status", "Model status", artifact.model_status, {source_component:"RISK_MODEL"}),
  ]);
}

export function inspectTool(gridId: string): ToolResult {
  const grid = getGrid(gridId), id = grid.grid_id;
  const evidence = [
    fact("risk_score","Risk score",grid.risk_score,{grid_id:id,source_component:"RISK_MODEL",unit:"/100"}),
    fact("risk_percentile_within_aoi","Risk percentile",grid.risk_percentile_within_aoi,{grid_id:id,source_component:"RISK_MODEL"}),
    fact("population_total","Population",grid.population_total,{grid_id:id,source_component:"WORLDPOP",unit:"people"}),
    fact("lst_median_c","LST median",grid.lst_median_c,{grid_id:id,source_component:"LANDSAT_9",unit:"°C"}),
    fact("green_fraction_land","Green fraction",grid.green_fraction_land,{grid_id:id,source_component:"SENTINEL_2"}),
    fact("water_fraction_grid","Water fraction",grid.water_fraction_grid,{grid_id:id,source_component:"SENTINEL_2"}),
    fact("elderly_share","Older adults share",grid.elderly_share,{grid_id:id,source_component:"WORLDPOP"}),
    fact("child_share","Children share",grid.child_share,{grid_id:id,source_component:"WORLDPOP"}),
    fact("hazard_contribution_points","Hazard contribution",grid.hazard_contribution_points,{grid_id:id,source_component:"RISK_MODEL",unit:"points"}),
    fact("exposure_contribution_points","Exposure contribution",grid.exposure_contribution_points,{grid_id:id,source_component:"RISK_MODEL",unit:"points"}),
    fact("vulnerability_contribution_points","Vulnerability contribution",grid.vulnerability_contribution_points,{grid_id:id,source_component:"RISK_MODEL",unit:"points"}),
    fact("adaptive_deficit_contribution_points","Adaptive deficit contribution",grid.adaptive_deficit_contribution_points,{grid_id:id,source_component:"RISK_MODEL",unit:"points"}),
    fact("risk_scale_max","Risk scale maximum",100,{source_component:"RISK_MODEL",unit:"points",method:"RISK_DISPLAY_SCALE_V1"}),
  ];
  if (typeof grid.risk_percentile_within_aoi === "number") evidence.push(fact("risk_percentile_percent","Risk percentile display",grid.risk_percentile_within_aoi * 100,{grid_id:id,source_component:"RISK_MODEL",unit:"%",method:"DISPLAY_PERCENTILE_V1"}));
  evidence.push(
    fact("analysis_status","Analysis status",grid.analysis_status,{grid_id:id,source_component:"RISK_MODEL"}),
    fact("landsat_quality_flag","Landsat quality flag",grid.landsat_quality_flag,{grid_id:id,source_component:"LANDSAT_9"}),
    fact("sentinel_quality_flag","Sentinel quality flag",grid.sentinel_quality_flag,{grid_id:id,source_component:"SENTINEL_2"}),
  );
  return toolResult("inspect_grid", gridData(grid), evidence);
}

function dominant(grid: Grid): string {
  return [["hazard",grid.hazard_contribution_points],["exposure",grid.exposure_contribution_points],["vulnerability",grid.vulnerability_contribution_points],["adaptive_capacity_deficit",grid.adaptive_deficit_contribution_points]].sort((a:any,b:any)=>b[1]-a[1])[0][0] as string;
}

export function hotspotsTool(limit = 10): ToolResult {
  const rows:any[] = [], evidence:Evidence[] = [], components:[string,string][] = [];
  artifact.summary.top_10_hotspots.slice(0, limit).forEach((hotspot:any,index:number) => {
    const grid = getGrid(hotspot.grid_id), rank = index + 1, component = dominant(grid);
    const row = {rank,grid_id:hotspot.grid_id,risk_score:hotspot.risk_score,risk_percentile_within_aoi:grid.risk_percentile_within_aoi,population_total:hotspot.population_total,primary_driver:grid.primary_driver,dominant_weighted_contribution:component};
    rows.push(row); components.push([row.grid_id,component]);
    evidence.push(fact("hotspot_rank",`Hotspot ${rank} rank`,rank,{grid_id:row.grid_id,source_component:"RISK_MODEL",unit:"rank"}));
    evidence.push(fact("risk_score",`Hotspot ${rank} risk`,row.risk_score,{grid_id:row.grid_id,source_component:"RISK_MODEL",unit:"/100"}));
    evidence.push(fact("population_total",`Hotspot ${rank} population`,row.population_total,{grid_id:row.grid_id,source_component:"WORLDPOP",unit:"people"}));
    evidence.push(fact("risk_percentile_percent",`Hotspot ${rank} percentile display`,grid.risk_percentile_within_aoi * 100,{grid_id:row.grid_id,source_component:"RISK_MODEL",unit:"%",method:"DISPLAY_PERCENTILE_V1"}));
  });
  evidence.push(fact("risk_scale_max","Risk scale maximum",100,{source_component:"RISK_MODEL",unit:"points",method:"RISK_DISPLAY_SCALE_V1"}));
  for (const [gridId, component] of components) evidence.push(fact("dominant_weighted_contribution","Largest weighted contribution component",component,{grid_id:gridId,source_component:"RISK_MODEL",method:"DOMINANT_WEIGHTED_CONTRIBUTION_V1"}));
  return toolResult("list_hotspots",rows,evidence,rows.length);
}

export function compareTool(ids: string[]): ToolResult {
  const selected = ids.map(getGrid), rows = selected.map(gridData), reference = selected[0];
  const deltas = selected.slice(1).map((grid) => ({from_grid_id:reference.grid_id,to_grid_id:grid.grid_id,risk_delta:delta(grid.risk_score,reference.risk_score),population_delta:delta(grid.population_total,reference.population_total),lst_delta:delta(grid.lst_median_c,reference.lst_median_c),green_delta:delta(grid.green_fraction_land,reference.green_fraction_land),hazard_delta:delta(grid.hazard_score,reference.hazard_score),exposure_score_delta:delta(grid.exposure_score,reference.exposure_score)}));
  const evidence:Evidence[] = [];
  for (const item of deltas) evidence.push(
    fact("risk_delta","Risk difference",item.risk_delta,{grid_id:item.to_grid_id,source_component:"RISK_MODEL",method:"COMPARE_DELTA_V1"}),
    fact("population_delta","Population difference",item.population_delta,{grid_id:item.to_grid_id,source_component:"WORLDPOP",method:"COMPARE_DELTA_V1"}),
    fact("lst_delta","LST difference",item.lst_delta,{grid_id:item.to_grid_id,source_component:"LANDSAT_9",method:"COMPARE_DELTA_V1"}),
    fact("green_delta","Green fraction difference",item.green_delta,{grid_id:item.to_grid_id,source_component:"SENTINEL_2",method:"COMPARE_DELTA_V1"}),
    fact("hazard_delta","Hazard score difference",item.hazard_delta,{grid_id:item.to_grid_id,source_component:"RISK_MODEL",method:"COMPARE_DELTA_V1"}),
    fact("exposure_score_delta","Exposure score difference",item.exposure_score_delta,{grid_id:item.to_grid_id,source_component:"RISK_MODEL",method:"COMPARE_DELTA_V1"}),
  );
  for (const grid of selected) evidence.push(fact("risk_score","Compared risk",grid.risk_score,{grid_id:grid.grid_id,source_component:"RISK_MODEL",unit:"/100"}),fact("population_total","Compared population",grid.population_total,{grid_id:grid.grid_id,source_component:"WORLDPOP",unit:"people"}));
  evidence.push(fact("risk_scale_max","Risk scale maximum",100,{source_component:"RISK_MODEL",unit:"points",method:"RISK_DISPLAY_SCALE_V1"}));
  for (const grid of selected) evidence.push(fact("comparison_grid","Pairwise comparison member",grid.grid_id,{grid_id:grid.grid_id,source_component:"RISK_MODEL",method:"PAIRWISE_COMPARISON_MEMBERSHIP_V1"}));
  return toolResult("compare_grids",{grids:rows,deltas},evidence,rows.length);
}

function delta(a:any,b:any):number|null { return typeof a === "number" && typeof b === "number" ? a-b : null; }
function matches(grid:Grid, condition:any):boolean { const actual=grid[condition.field], value=condition.value; switch(condition.op){case"eq":return actual===value;case"gt":return typeof actual==="number"&&actual>value;case"gte":return typeof actual==="number"&&actual>=value;case"lt":return typeof actual==="number"&&actual<value;case"lte":return typeof actual==="number"&&actual<=value;case"in":return Array.isArray(value)&&value.includes(actual);default:return false;} }

export function queryTool(input:any):ToolResult {
  const filters=input.filters ?? [], sortBy=input.sort_by ?? "risk_score", sortOrder=input.sort_order ?? "desc", limit=input.limit ?? 10;
  const matched=grids.filter((grid)=>filters.every((condition:any)=>matches(grid,condition)));
  matched.sort((a,b)=>String(a.grid_id).localeCompare(String(b.grid_id)));
  matched.sort((a,b)=>{const av=a[sortBy],bv=b[sortBy];if(sortOrder==="desc"){if(av==null)return 1;if(bv==null)return -1;return bv-av;}if(av==null)return 1;if(bv==null)return -1;return av-bv;});
  const rows=matched.slice(0,limit).map(gridData), evidence:Evidence[]=[fact("query_result_count","Query result count",rows.length,{source_component:"RISK_MODEL",unit:"grids"}),fact("query_total_match_count","Query total matches",matched.length,{source_component:"RISK_MODEL",unit:"grids"})];
  for(const row of rows){evidence.push(fact("grid_result","Query result",row.grid_id,{grid_id:row.grid_id,source_component:"RISK_MODEL"}));for(const [metric,component] of [["population_total","WORLDPOP"],["lst_median_c","LANDSAT_9"],["exposure_score","RISK_MODEL"],["green_fraction_land","SENTINEL_2"],["risk_score","RISK_MODEL"]])if(row[metric]!=null)evidence.push(fact(metric,`Query ${metric}`,row[metric],{grid_id:row.grid_id,source_component:component}));}
  evidence.push(fact("risk_scale_max","Risk scale maximum",100,{source_component:"RISK_MODEL",unit:"points",method:"RISK_DISPLAY_SCALE_V1"}));
  for(const condition of filters){if(!["gt","gte","lt","lte"].includes(condition.op)){evidence.push(fact("query_filter",`${condition.field} filter`,condition.value,{source_component:"RISK_MODEL",method:"AGENT_QUERY_RELATIVE_SEMANTICS_V2"}));continue;}let method="AGENT_QUERY_RELATIVE_SEMANTICS_V2";if(["green_fraction_land","lst_median_c","risk_score"].includes(condition.field)){if(Math.abs(condition.value-percentile(condition.field,.75))<=1e-12)method="DEMO_AOI_P75";else if(Math.abs(condition.value-percentile(condition.field,.25))<=1e-12)method="DEMO_AOI_P25";}const component=condition.field==="green_fraction_land"?"SENTINEL_2":condition.field==="lst_median_c"?"LANDSAT_9":condition.field==="population_total"?"WORLDPOP":"RISK_MODEL";evidence.push(fact("query_threshold",`${condition.field} threshold`,condition.value,{source_component:component,method}));}
  evidence.push(fact("query_sort","Query sort field",sortBy,{source_component:"RISK_MODEL",method:`QUERY_SORT_${sortOrder.toUpperCase()}`}));
  return toolResult("query_grids",rows,evidence,rows.length);
}

export function explainTool(gridId:string):ToolResult {
  const inspected=inspectTool(gridId), grid=getGrid(gridId), parts:any[]=[["hazard",grid.hazard_contribution_points],["exposure",grid.exposure_contribution_points],["vulnerability",grid.vulnerability_contribution_points],["adaptive_capacity_deficit",grid.adaptive_deficit_contribution_points]];
  const available=grid.risk_score!=null, ordered=available?parts.sort((a,b)=>b[1]-a[1]):[];
  inspected.tool_name="explain_risk"; inspected.data={...inspected.data,primary_driver:available?grid.primary_driver:null,contribution_ranking:ordered.map(([component,points])=>({component,points})),largest_contribution:ordered[0]?.[0]??null,second_largest_contribution:ordered[1]?.[0]??null,risk_available:available};
  if(ordered.length)inspected.evidence.push(fact("dominant_weighted_contribution","Largest weighted contribution",ordered[0][0],{grid_id:grid.grid_id,source_component:"RISK_MODEL",method:"DOMINANT_WEIGHTED_CONTRIBUTION_V1"}));
  return inspected;
}

const METHODS:Record<string,any>={overview:"HeatSafe is a read-only relative heat-risk diagnostic for the selected 5 km x 5 km analysis area.",risk_formula:"Risk = 0.40 H + 0.25 E + 0.20 V + 0.15 (1-A).",risk_scope:"Scores are relative within the selected analysis area, not mortality, health-outcome, or citywide absolute probabilities.",hazard:"Hazard combines 0.7 within-AOI spatial LST percentile with 0.3 shared ERA5-Land temporal severity.",exposure:"Exposure is the normalized log1p population proxy for each analysis grid.",vulnerability:"Vulnerability = 0.7 elderly share (65+) + 0.3 child share (0-14).",adaptive_capacity:"Adaptive capacity is a vegetation-based proxy from green fraction among valid land pixels; the risk term is 1-A.",worldpop:"WorldPop 2026 official R2025A 100 m products are transferred to 250 m grids by fractional-area count transfer.",landsat:"Landsat 9 surface temperature observations use a 100 m thermal source aggregated to 250 m grids.",sentinel2:"Sentinel-2 10 m optical observations provide NDVI, green fraction, and water classification aggregated to 250 m grids.",era5:"ERA5-Land supplies shared temporal heat context for the analysis area; no artificial 250 m spatial variation is created.",water_rule:"Cells with water fraction >= 0.50 are NON_URBAN_WATER and have no risk score.",qa:artifact.qa_contract_version,limitations:"The model is PRELIMINARY_HEURISTIC and supports relative within-AOI prioritization only; it does not estimate mortality, health outcomes, or causal intervention effects."};
export function methodologyTool(topic:string):ToolResult {const value=METHODS[topic];return toolResult("get_methodology",{topic,text:value,methods:artifact.methods,risk_scope:artifact.risk_scope},[fact("methodology",topic,value,{source_component:"RISK_MODEL",source_ref:"m4c1_qa_contract"})]);}

export function executeTool(name:string,payload:any):ToolResult {
  switch(name){case"get_demo_summary":return summaryTool();case"inspect_grid":return inspectTool(payload.grid_id);case"list_hotspots":return hotspotsTool(payload.limit??10);case"compare_grids":return compareTool(payload.grid_ids);case"query_grids":return queryTool(payload);case"explain_risk":return explainTool(payload.grid_id);case"get_methodology":return methodologyTool(payload.topic);default:throw new Error(`unknown public tool: ${name}`);}
}
