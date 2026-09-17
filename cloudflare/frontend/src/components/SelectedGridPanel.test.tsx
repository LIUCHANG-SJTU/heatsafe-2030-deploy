import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { DemoGridDetail, GridActionPlan } from "../api/types";
import { SelectedGridPanel } from "./SelectedGridPanel";
import { I18nProvider } from "../i18n/I18nProvider";

const waterGrid = { grid_id: "M4B-R-5EEC8B7710-G-R00-C08", analysis_status: "NON_URBAN_WATER", analysis_reasons: ["WATER_EXCLUDED"], ranking_eligible: false, source_mode: "REAL", population_total: 22, population_age_0_14: 2, population_age_65_plus: 3, elderly_share: .1, child_share: .1, vulnerability_share_raw: .1, lst_median_c: 35, landsat_quality_flag: "HIGH", ndvi_median_land: null, green_fraction_land: null, green_fraction_grid_legacy: null, water_fraction_grid: .8, sentinel_valid_fraction: 1, sentinel_quality_flag: "HIGH", spatial_heat_score: null, temporal_severity_score: .5, hazard_score: null, exposure_score: null, vulnerability_score: null, adaptive_capacity_score: null, risk_score: null, risk_percentile_within_aoi: null, H: null, E: null, V: null, A: null, hazard_contribution_points: null, exposure_contribution_points: null, vulnerability_contribution_points: null, adaptive_deficit_contribution_points: null, primary_driver: null, temporal_context_id: "era5", source_ids: [], row: 0, column: 0, geometry: {}, methods: {}, quality: {}, provenance: {}, temporal_context: null } as DemoGridDetail;
const landGrid = { ...waterGrid, grid_id: "M4B-R-5EEC8B7710-G-R16-C13", analysis_status: "ANALYZABLE_LAND", primary_driver: "hazard", water_fraction_grid: .1, risk_score: 90.2, risk_percentile_within_aoi: 1, hazard_contribution_points: 33.6, exposure_contribution_points: 25, vulnerability_contribution_points: 20, adaptive_deficit_contribution_points: 11.6 } as DemoGridDetail;
const actionPlan = { scope: "grid", grid_id: "GRID-1", risk_score: 90.2, risk_scope: "RELATIVE_WITHIN_DEMO_AOI", recommendation_status: "DECISION_SUPPORT_HEURISTIC", action_cards: [], guidance: [] } as GridActionPlan;

describe("SelectedGridPanel", () => {
  beforeEach(() => {
    localStorage.clear();
    HTMLElement.prototype.scrollIntoView = vi.fn();
  });
  it("renders water risk as N/A rather than zero", () => {
    render(<I18nProvider><SelectedGridPanel grid={waterGrid} /></I18nProvider>);
    expect(screen.getByText("N/A")).toBeInTheDocument();
    expect(screen.getByText(/水域占比/)).toBeInTheDocument();
  });
  it("keeps risk details visible when the action request fails", () => {
    render(<I18nProvider><SelectedGridPanel grid={landGrid} actionPlan={null} actionError="Action plan unavailable" /></I18nProvider>);
    expect(screen.getByText("相对风险")).toBeInTheDocument();
    expect(screen.getByText("90.2")).toBeInTheDocument();
    expect(screen.getByText("行动建议暂不可用")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "格网 R16-C13" })).toHaveAttribute("title", landGrid.grid_id);
    expect(screen.getByText("最大加权贡献项")).toBeInTheDocument();
    expect(screen.getByText("最大贡献项不代表因果作用。")).toBeInTheDocument();
  });
  it("provides a localized action shortcut that scrolls to and focuses the existing action plan", () => {
    render(<I18nProvider><SelectedGridPanel grid={landGrid} actionPlan={actionPlan} /></I18nProvider>);
    const actionSection = document.querySelector<HTMLElement>("#action-plan");
    expect(actionSection).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "查看优先行动" }));
    expect(actionSection?.scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "start" });
    expect(actionSection).toHaveFocus();
  });
  it("localizes the action shortcut in English", () => {
    localStorage.setItem("heatsafe-locale", "en");
    render(<I18nProvider><SelectedGridPanel grid={landGrid} actionPlan={actionPlan} /></I18nProvider>);
    expect(screen.getByRole("button", { name: "View Priority Actions" })).toBeInTheDocument();
  });
});
