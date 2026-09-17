import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { GridActionPlan } from "../api/types";
import { I18nProvider } from "../i18n/I18nProvider";
import { ActionPlanPanel } from "./ActionPlanPanel";


const plan: GridActionPlan = {
  scope: "grid",
  grid_id: "GRID-1",
  risk_score: 90.2,
  risk_scope: "RELATIVE_WITHIN_DEMO_AOI",
  recommendation_status: "DECISION_SUPPORT_HEURISTIC",
  action_cards: [
    {
      priority_rank: 2,
      action_family: "POPULATION_EXPOSURE_MANAGEMENT",
      title_zh: "人口暴露管理",
      title_en: "Population Exposure Management",
      recommended_actions_zh: ["加强高温信息与公共服务触达"],
      recommended_actions_en: ["Strengthen service reach"],
      why_zh: "Exposure contribution",
      why_en: "Existing exposure contribution sets this priority.",
      signal_metric: "exposure_contribution_points",
      signal_points: 25,
      supporting_evidence: [{ evidence_id: "E9", metric: "population_total", grid_id: "GRID-1", value: 1589.3 }],
      guidance_ids: ["WHO_HHAP_2026_COMMUNICATION"],
      recommendation_status: "DECISION_SUPPORT_HEURISTIC",
      effect_estimate: null,
      limitation_zh: "不代表措施实施后的风险下降幅度。",
      limitation_en: "This is not a predicted risk reduction.",
    },
    {
      priority_rank: 1,
      action_family: "HEAT_EXPOSURE_MITIGATION",
      title_zh: "热暴露缓解",
      title_en: "Heat Exposure Mitigation",
      recommended_actions_zh: ["优先评估公共活动空间遮阴条件", "加强高温时段热暴露管理"],
      recommended_actions_en: ["Assess shade", "Manage exposure"],
      why_zh: "Hazard contribution",
      why_en: "Existing hazard contribution sets this priority.",
      signal_metric: "hazard_contribution_points",
      signal_points: 33.6,
      supporting_evidence: [
        { evidence_id: "E4", metric: "hazard_contribution_points", grid_id: "GRID-1", value: 33.6 },
        { evidence_id: "E7", metric: "lst_median_c", grid_id: "GRID-1", value: 51.2 },
      ],
      guidance_ids: ["WHO_HHAP_2026_REDUCE_EXPOSURE", "UNHABITAT_UHM_2025_PASSIVE_COOLING"],
      recommendation_status: "DECISION_SUPPORT_HEURISTIC",
      effect_estimate: null,
      limitation_zh: "不代表措施实施后的风险下降幅度。",
      limitation_en: "This is not a predicted risk reduction.",
    },
  ],
  guidance: [
    { guidance_id: "WHO_HHAP_2026_REDUCE_EXPOSURE", organization_zh: "世界卫生组织欧洲区域办事处", organization_en: "World Health Organization", title_zh: "高温健康行动计划指南（第二版）", title_en: "Heat-health action plans", year: 2026, section_zh: "减少热暴露", section_en: "Reduce exposure", url: "https://www.who.int/example" },
    { guidance_id: "WHO_HHAP_2026_COMMUNICATION", organization_zh: "世界卫生组织欧洲区域办事处", organization_en: "World Health Organization", title_zh: "高温健康行动计划指南（第二版）", title_en: "Heat-health action plans", year: 2026, section_zh: "信息沟通", section_en: "Communication", url: "https://www.who.int/example" },
    { guidance_id: "UNHABITAT_UHM_2025_PASSIVE_COOLING", organization_zh: "联合国人居署 / 世界银行 / 联合国环境署", organization_en: "UN-Habitat / World Bank / UNEP", title_zh: "全球南方城市热管理手册", title_en: "Urban Heat Management", year: 2025, section_zh: "被动降温", section_en: "Passive cooling", url: "https://unhabitat.org/example" },
  ],
};


describe("ActionPlanPanel", () => {
  const renderPanel = (ui: React.ReactNode) => render(<I18nProvider>{ui}</I18nProvider>);

  it("renders priority cards in deterministic rank order", () => {
    const { container } = renderPanel(<ActionPlanPanel plan={plan} />);
    const cards = Array.from(container.querySelectorAll(".action-card"));
    expect(cards).toHaveLength(2);
    expect(cards[0]).toHaveTextContent("优先级 1");
    expect(cards[0]).toHaveTextContent("热暴露缓解");
    expect(cards[1]).toHaveTextContent("优先级 2");
  });

  it("shows why evidence, guidance badges, and decision boundary", () => {
    renderPanel(<ActionPlanPanel plan={plan} />);
    expect(screen.getAllByText(/热危险度加权贡献/i).length).toBeGreaterThan(0);
    expect(screen.getByText("E4")).toBeInTheDocument();
    expect(screen.getByText("E7")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /WHO/ }).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /UN-Habitat/ })).toBeInTheDocument();
    expect(screen.getByText(/不代表措施实施后的风险下降幅度/)).toBeInTheDocument();
    expect(screen.queryByText(/effect estimate/i)).not.toBeInTheDocument();
  });

  it("renders bounded loading and error states", () => {
    const { rerender } = renderPanel(<ActionPlanPanel plan={null} loading />);
    expect(screen.getByText("正在读取行动优先级…")).toBeInTheDocument();
    rerender(<I18nProvider><ActionPlanPanel plan={null} error="Action plan unavailable" /></I18nProvider>);
    expect(screen.getByText("行动建议暂不可用")).toBeInTheDocument();
  });

  it("shows only the active English action copy", () => {
    localStorage.setItem("heatsafe-locale", "en");
    renderPanel(<ActionPlanPanel plan={plan} />);
    expect(screen.getByText("Heat Exposure Mitigation")).toBeInTheDocument();
    expect(screen.getByText("Existing hazard contribution sets this priority.")).toBeInTheDocument();
    expect(screen.getByText("This is not a predicted risk reduction.")).toBeInTheDocument();
    expect(screen.queryByText("热暴露缓解")).not.toBeInTheDocument();
    expect(screen.queryByText("优先评估公共活动空间遮阴条件")).not.toBeInTheDocument();
  });
});
