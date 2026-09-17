import { describe, expect, it, vi } from "vitest";
import { demoApi } from "./demoApi";

describe("demo API client", () => {
  it("parses summary and grid collection responses", async () => {
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ api_version: "v1", data_mode: "REAL", summary: {} }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ type: "FeatureCollection", features: [] }), { status: 200 })));
    expect((await demoApi.summary()).api_version).toBe("v1");
    expect((await demoApi.grids()).type).toBe("FeatureCollection");
    vi.unstubAllGlobals();
  });
  it("surfaces API errors", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "unavailable" }), { status: 503 })));
    await expect(demoApi.summary()).rejects.toThrow("unavailable");
    vi.unstubAllGlobals();
  });
  it("loads a grounded action plan for a grid", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ grid_id: "GRID-1", action_cards: [] }), { status: 200 })));
    expect((await demoApi.actionsForGrid("GRID-1")).grid_id).toBe("GRID-1");
    expect(fetch).toHaveBeenCalledWith("/api/v1/actions/grid/GRID-1");
    vi.unstubAllGlobals();
  });
});
