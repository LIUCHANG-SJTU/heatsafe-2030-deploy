import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AgentEvidence } from "./AgentEvidence";
import { I18nProvider } from "../i18n/I18nProvider";

describe("AgentEvidence", () => {
  beforeEach(() => localStorage.clear());
  it("renders grounded source cards and map action", async () => {
    const onGridClick = vi.fn();
    render(<I18nProvider><AgentEvidence items={[{ evidence_id: "E1", metric: "risk_score", label: "Risk score", value: 77.4727, unit: "/100", grid_id: "GRID-1", source_component: "RISK_MODEL", source_ref: "heatsafe_demo_v1_2026", data_mode: "REAL" }]} onGridClick={onGridClick} /></I18nProvider>);
    expect(screen.getByText(/热风险/)).toBeInTheDocument();
    expect(screen.getByText("77.5")).toBeInTheDocument();
    screen.getByRole("button").click();
    expect(onGridClick).toHaveBeenCalledWith("GRID-1");
  });

  it("keeps cited evidence visible beyond the default card limit and formats percentiles", () => {
    const items = Array.from({ length: 13 }, (_, index) => ({
      evidence_id: `E${index + 1}`,
      metric: index === 1 ? "risk_percentile_within_aoi" : index === 12 ? "risk_percentile_percent" : "fact",
      label: index === 12 ? "Risk percentile display" : `Fact ${index + 1}`,
      value: index === 1 ? 1 : index === 12 ? 100 : "ok",
      unit: index === 12 ? "%" : null,
      grid_id: "GRID-1",
      source_component: "RISK_MODEL",
      source_ref: "demo",
      data_mode: "REAL",
    }));
    render(<I18nProvider><AgentEvidence items={items} citedEvidenceIds={["E13"]} onGridClick={vi.fn()} /></I18nProvider>);
    expect(screen.getByText("[E13]")).toBeInTheDocument();
    expect(screen.getAllByText("100.0%")).toHaveLength(2);
    expect(screen.queryByText("[E12]")).not.toBeInTheDocument();
  });

  it("uses English metric and source labels in English mode", () => {
    localStorage.setItem("heatsafe-locale", "en");
    render(<I18nProvider><AgentEvidence items={[{ evidence_id: "E1", metric: "risk_score", label: "风险分数", value: 77.5, unit: "/100", grid_id: "GRID-1", source_component: "RISK_MODEL", source_ref: "demo", data_mode: "REAL" }]} onGridClick={vi.fn()} /></I18nProvider>);
    expect(screen.getByText(/Heat Risk/)).toBeInTheDocument();
    expect(screen.getByText("Risk Model")).toBeInTheDocument();
    expect(screen.queryByText(/风险分数/)).not.toBeInTheDocument();
  });

  it("formats population and land fractions for people rather than machines", () => {
    render(<I18nProvider><AgentEvidence items={[
      { evidence_id: "E3", metric: "population_total", label: "Population", value: 1589.3, unit: "people", grid_id: "GRID-1", source_component: "WORLDPOP", source_ref: "demo", data_mode: "REAL" },
      { evidence_id: "E5", metric: "green_fraction_land", label: "Green fraction", value: 0.2, unit: "fraction", grid_id: "GRID-1", source_component: "SENTINEL2", source_ref: "demo", data_mode: "REAL" },
    ]} onGridClick={vi.fn()} /></I18nProvider>);
    expect(screen.getByText("约 1,589 人")).toBeInTheDocument();
    expect(screen.getByText("20.0%")).toBeInTheDocument();
  });
});
