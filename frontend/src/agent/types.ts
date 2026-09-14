export interface AgentEvidence {
  evidence_id: string;
  metric: string;
  label: string;
  value: unknown;
  unit?: string | null;
  grid_id?: string | null;
  source_component: string;
  source_ref: string;
  data_mode: string;
  qa_status?: string | null;
}

export interface AgentMapAction {
  action: "select_grid" | "highlight_grids" | "focus_grids" | "suggest_layer";
  grid_ids: string[];
  layer?: string | null;
}

export interface AgentResponse {
  request_id: string;
  answer: string;
  evidence: AgentEvidence[];
  tool_trace: Array<{ tool_name: string; status: string; result_count: number }>;
  map_actions: AgentMapAction[];
  validation: { status: "PASS" | "FAIL"; errors: string[] };
  answer_mode: "GROUNDED" | "DETERMINISTIC_FALLBACK" | "SCOPE_LIMITATION";
  provider: string;
  model: string;
  latency_ms: number;
}

export interface AgentMessage {
  role: "user" | "assistant";
  content: string;
}

export interface AgentContext {
  locale: "zh-CN" | "en";
  selected_grid_id?: string | null;
  active_layer?: string | null;
  focused_hotspot_id?: string | null;
  agent_highlighted_grid_ids?: string[];
}
