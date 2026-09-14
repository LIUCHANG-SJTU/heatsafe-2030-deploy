import type { DemoGridCollection, DemoGridDetail, DemoSummary, GridActionPlan } from "./types";

const apiBase = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
const useFixture = import.meta.env.VITE_USE_FIXTURE === "true";

async function request<T>(path: string, fixturePath?: string): Promise<T> {
  if (useFixture && fixturePath) {
    const response = await fetch(`/fixtures/demo_api_v1/${fixturePath}`);
    if (!response.ok) throw new Error(`Fixture request failed (${response.status})`);
    return response.json() as Promise<T>;
  }
  const response = await fetch(`${apiBase}/api/v1${path}`);
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try { detail = (await response.json()).detail || detail; } catch { /* preserve status */ }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export const demoApi = {
  summary: () => request<DemoSummary>("/demo", "demo.json"),
  grids: () => request<DemoGridCollection>("/demo/grids", "grids.geojson"),
  grid: (gridId: string) => request<DemoGridDetail>(`/demo/grids/${encodeURIComponent(gridId)}`, "grid_detail_example.json"),
  actionsForGrid: (gridId: string) => request<GridActionPlan>(`/actions/grid/${encodeURIComponent(gridId)}`),
};

export { useFixture };
