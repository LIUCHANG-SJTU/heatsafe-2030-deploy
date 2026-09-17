import { Evidence, MapAction } from "./contracts";

const REF=/\[E(\d+)\]/g;
const NUMBER=/(?<![A-Za-z0-9])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?(?:°C)?(?![A-Za-z])/g;
const FORBIDDEN=/死亡概率|患病概率|mortality probability|health[- ]outcome probability|杭州市级|杭州全市|citywide absolute|增加\s*\d+%?.*风险|what if|counterfactual|scenario/i;
const ABSOLUTE=/地表温度极端|人口密集|敏感人群比例较高|extreme heatwave|persistent extreme/i;

export type Validation={status:"PASS"|"FAIL";errors:string[]};

export function validateAnswer(answer:string,evidence:Evidence[],mapActions:MapAction[]=[]):Validation{
  const errors:string[]=[], byId=new Map(evidence.filter(item=>item.evidence_id).map(item=>[item.evidence_id!,item]));
  const refs=[...answer.matchAll(REF)].map(match=>`E${match[1]}`), numbers=[...answer.matchAll(NUMBER)];
  if(!refs.length&&numbers.length)errors.push("quantitative answer must cite evidence");
  for(const ref of refs)if(!byId.has(ref))errors.push(`unknown evidence reference: ${ref}`);
  const lower=answer.toLowerCase(), disclaimer=["不代表","不是","not a","does not","not mortality","not health","不支持"].some(marker=>lower.includes(marker));
  if(FORBIDDEN.test(answer)&&!disclaimer)errors.push("forbidden scope or scenario claim");
  if(ABSOLUTE.test(answer))errors.push("unsupported absolute wording; describe conditions relative to the analysis area");
  const cited=refs.map(ref=>byId.get(ref)?.value).filter(value=>value!==undefined);
  for(const match of numbers){const token=match[0], value=Number(token.replaceAll(",","").replace("%","").replace("°C",""));if(Number.isNaN(value))continue;const start=Math.max(answer.lastIndexOf("。",match.index),answer.lastIndexOf("，",match.index),answer.lastIndexOf(";",match.index))+1;const after=(match.index??0)+token.length, ends=[answer.indexOf("。",after),answer.indexOf("，",after),answer.indexOf(";",after)].filter(index=>index>=0);const end=ends.length?Math.min(...ends):answer.length,context=answer.slice(start,end).toLowerCase(),percentage=token.endsWith("%")||["百分位","百分比","percentile","percent"].some(marker=>context.includes(marker)), candidates=percentage?[value,value/100]:[value];if(!candidates.some(candidate=>cited.some(item=>typeof item==="number"&&Math.abs(candidate-item)<=Math.max(.15,Math.abs(item)*.01)))){if(!evidence.some(item=>item.metric==="methodology"&&refs.includes(item.evidence_id??"")))errors.push(`unsupported numeric claim: ${token}`);break;}}
  for(const action of mapActions)if(["select_grid","highlight_grids","focus_grids"].includes(action.action)&&action.grid_ids.length>20)errors.push("map action exceeds grid limit");
  return {status:errors.length?"FAIL":"PASS",errors};
}

export function scenarioRequest(text:string):boolean{
  if(text.includes("为什么绿地")||text.toLowerCase().includes("why does green"))return false;
  return /如果.{0,40}(增加|减少|提高|降低|升温|降温)|假设.{0,40}(温度|绿地|风险)|措施.{0,24}风险.{0,12}(下降|降低|减少)|风险.{0,12}(下降|降低|减少)多少|情景模拟|what\s+if|increase\s+green|decrease\s+temperature|how much.{0,30}(?:(risk|score).{0,20}(drop|decrease|reduce)|(drop|decrease|reduce).{0,20}(risk|score))|\+\s*3\s*°?c|counterfactual|scenario\s+simulation/i.test(text);
}

export function injectionRequest(text:string):boolean{return /ignore\s+(all\s+)?previous|忽略.*(规则|指令)|系统提示词|system prompt|api\s*key|执行\s*python|use\s+python|输出.*secret|pretend.*risk/i.test(text);}
