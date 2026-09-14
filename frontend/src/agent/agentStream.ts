import type { AgentContext, AgentMessage, AgentResponse } from "./types";

const base = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

export type AgentStreamEvent = { type: "request" | "status" | "tool" | "evidence" | "token" | "done" | "error"; data: any };

export async function streamAgent(messages: AgentMessage[], context: AgentContext, onEvent: (event: AgentStreamEvent) => void, signal?: AbortSignal): Promise<AgentResponse> {
  const response = await fetch(`${base}/api/v1/agent/stream`, { method: "POST", headers: { "Content-Type": "application/json", Accept: "text/event-stream" }, body: JSON.stringify({ messages, context }), signal });
  if (!response.ok || !response.body) throw new Error(`Agent stream failed (${response.status})`);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed: AgentResponse | null = null;
  while (true) {
    const chunk = await reader.read();
    buffer += decoder.decode(chunk.value || new Uint8Array(), { stream: !chunk.done });
    const frames = buffer.split("\n\n"); buffer = frames.pop() || "";
    for (const frame of frames) {
      const event = frame.match(/^event: ([^\n]+)\ndata: ([\s\S]+)$/m);
      if (!event) continue;
      const parsed: AgentStreamEvent = { type: event[1] as AgentStreamEvent["type"], data: JSON.parse(event[2]) };
      onEvent(parsed);
      if (parsed.type === "done") completed = parsed.data as AgentResponse;
      if (parsed.type === "error") throw new Error(parsed.data.message || "Agent request failed");
    }
    if (chunk.done) break;
  }
  if (!completed) throw new Error("Agent stream ended without done event");
  return completed;
}
