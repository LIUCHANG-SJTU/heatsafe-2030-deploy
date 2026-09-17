import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

vi.mock("./components/MapView", () => ({ MapView: () => <div data-testid="map" /> }));
vi.mock("./hooks/useDemo", () => ({
  useDemo: () => ({
    data: {
      data_mode: "REAL",
      qa_contract_version: "M4C1_CANONICAL_QA_V1",
      aoi: { event: { date: "2026-07-31" } },
      temporal_context: { temporal_severity_score: 0.75 },
      summary: {
        total_grid_count: 400,
        analyzable_land_grid_count: 315,
        water_excluded_grid_count: 85,
        water_excluded_population_fraction: 0.01,
        total_population_est: 244916,
        risk_p90: 75,
        top_10_hotspots: [],
      },
    },
    isError: false,
  }),
  useDemoGrids: () => ({ data: { type: "FeatureCollection", features: [] }, isError: false }),
  useGridDetail: () => ({ data: null, isLoading: false }),
  useGridActions: () => ({ data: null, isLoading: false, error: null }),
}));

describe("application localization", () => {
  beforeEach(() => localStorage.clear());

  it("renders Chinese navigation, hero, and KPI copy by default", () => {
    render(<App />);
    expect(screen.getByRole("link", { name: "总览" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "看见热风险，行动有依据。" })).toBeInTheDocument();
    expect(screen.getByText("生产格网总数")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "HeatSafe 智能决策助手" })).toHaveAttribute("title", "HeatSafe 智能决策助手");
    expect(document.body.textContent).not.toMatch(/Demo(?: AOI)?/i);
    expect(document.body.textContent).not.toContain("Map Analysis");
    expect(document.body.textContent).not.toContain("Recommended Actions");
    expect(document.body.textContent).not.toContain("Data & Methodology");
  });

  it("renders representative competition UI in English without ordinary Chinese copy", () => {
    localStorage.setItem("heatsafe-locale", "en");
    render(<App />);
    expect(screen.getByRole("link", { name: "Overview" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "See the heat risk. Act on evidence." })).toBeInTheDocument();
    expect(screen.getByText("Total Grids")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "ZH" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "HeatSafe Decision Agent" })).toHaveAttribute("title", "HeatSafe Decision Agent");
    expect(document.body.textContent).not.toMatch(/\bDemo(?: AOI)?\b/i);
    expect(document.body.textContent).not.toMatch(/[\u4e00-\u9fff]/);
  });
});
