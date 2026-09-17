import type { AgentContext, AgentMessage, AgentResponse } from "./types";

const base = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

export async function getAgentStatus(): Promise<{ enabled: boolean; provider_kind: string; model: string; tools: string[]; scenario_simulation: boolean }> {
  const response = await fetch(`${base}/api/v1/agent/status`);
  if (!response.ok) throw new Error(`Agent status failed (${response.status})`);
  return response.json();
}

export async function queryAgent(messages: AgentMessage[], context: AgentContext, signal?: AbortSignal): Promise<AgentResponse> {
  const response = await fetch(`${base}/api/v1/agent/query`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ messages, context }), signal });
  if (!response.ok) throw new Error((await response.text()) || `Agent request failed (${response.status})`);
  return response.json();
}
