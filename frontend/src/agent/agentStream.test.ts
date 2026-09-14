import { describe, expect, it, vi } from "vitest";
import { streamAgent } from "./agentStream";

describe("agent stream parser", () => {
  it("parses event frames split across chunks", async () => {
    const encoder = new TextEncoder();
    const chunks = ["event: request\ndata: {\"request_id\":\"r1\"}\n\n", "event: done\ndata: {\"request_id\":\"r1\",\"answer\":\"ok\",\"evidence\":[],\"tool_trace\":[],\"map_actions\":[],\"validation\":{\"status\":\"PASS\",\"errors\":[]},\"answer_mode\":\"DETERMINISTIC_FALLBACK\",\"provider\":\"deterministic\",\"model\":\"fallback-v1\",\"latency_ms\":1}\n\n"];
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, body: { getReader: () => { let index = 0; return { read: async () => index < chunks.length ? { done: false, value: encoder.encode(chunks[index++]) } : { done: true, value: undefined } }; } } }));
    const events: string[] = [];
    const result = await streamAgent([{ role: "user", content: "hello" }], { locale: "zh-CN" }, (event) => events.push(event.type));
    expect(events).toEqual(["request", "done"]);
    expect(result.answer).toBe("ok");
    vi.unstubAllGlobals();
  });

  it("treats token events as deltas and done as the canonical answer", async () => {
    const encoder = new TextEncoder();
    const chunks = [
      "event: token\ndata: {\"text\":\"ABC \"}\n\nevent: token\ndata: {\"text\":\"DEF\"}\n\n",
      "event: done\ndata: {\"request_id\":\"r1\",\"answer\":\"ABC DEF\",\"evidence\":[],\"tool_trace\":[],\"map_actions\":[],\"validation\":{\"status\":\"PASS\",\"errors\":[]},\"answer_mode\":\"GROUNDED\",\"provider\":\"mock\",\"model\":\"mock\",\"latency_ms\":1}\n\n",
    ];
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, body: { getReader: () => { let index = 0; return { read: async () => index < chunks.length ? { done: false, value: encoder.encode(chunks[index++]) } : { done: true, value: undefined } }; } } }));
    let draft = "";
    const result = await streamAgent([{ role: "user", content: "hello" }], { locale: "zh-CN" }, (event) => { if (event.type === "token") draft += event.data.text; });
    expect(draft).toBe("ABC DEF");
    expect(result.answer).toBe("ABC DEF");
    vi.unstubAllGlobals();
  });
});
