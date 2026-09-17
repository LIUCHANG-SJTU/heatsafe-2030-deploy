export type Grid = Record<string, any>;

export type Evidence = {
  evidence_id: string | null;
  metric: string;
  label: string;
  value: any;
  unit: string | null;
  grid_id: string | null;
  source_component: string;
  source_ref: string;
  method: string | null;
  data_mode: string;
  qa_status: string | null;
};

export type ToolResult = {
  tool_name: string;
  data: any;
  evidence: Evidence[];
  result_count: number;
};

export type MapAction = {
  action: "select_grid" | "highlight_grids" | "focus_grids" | "suggest_layer";
  grid_ids: string[];
  layer: string | null;
};

export function fact(metric: string, label: string, value: any, extra: Partial<Evidence> = {}): Evidence {
  return {
    evidence_id: null,
    metric,
    label,
    value,
    unit: null,
    grid_id: null,
    source_component: "DEMO_METADATA",
    source_ref: "heatsafe_demo_v1_2026",
    method: null,
    data_mode: "REAL",
    qa_status: null,
    ...extra,
  };
}

function bindRefs(value: any, evidence: Evidence[]): any {
  if (Array.isArray(value)) return value.map((item) => bindRefs(item, evidence));
  if (!value || typeof value !== "object") return value;
  const rebound = Object.fromEntries(Object.entries(value).map(([key, item]) => [key, bindRefs(item, evidence)]));
  if ("evidence_id" in rebound && "metric" in rebound && "value" in rebound) {
    const match = evidence.find((item) => item.metric === rebound.metric && item.grid_id === (rebound.grid_id ?? null) && item.value === rebound.value);
    if (match) rebound.evidence_id = match.evidence_id;
  }
  return rebound;
}

export class EvidenceLedger {
  private items: Evidence[] = [];

  append(result: ToolResult): ToolResult {
    const offset = this.items.length;
    const assigned = result.evidence.map((item, index) => ({...item, evidence_id: `E${offset + index + 1}`}));
    this.items.push(...assigned);
    return {...result, evidence: assigned, data: bindRefs(result.data, assigned)};
  }

  all(): Evidence[] { return [...this.items]; }
}

export function toolResult(tool_name: string, data: any, evidence: Evidence[], result_count = 1): ToolResult {
  return {tool_name, data, evidence, result_count};
}
