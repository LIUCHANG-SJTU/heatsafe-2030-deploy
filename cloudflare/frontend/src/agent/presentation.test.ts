import { describe, expect, it } from "vitest";
import { presentAgentAnswer } from "./presentation";

const gridId = "M4B-R-5EEC8B7710-G-R16-C13";

describe("Agent answer presentation", () => {
  it("presents the deterministic Chinese answer as an intentional grounded mode", () => {
    const raw = `当前模型服务暂时不可用，以下为 HeatSafe REAL 数据摘要。格网 ${gridId} 的相对风险为 90.2 [E1]，主要贡献项为 hazard。\n该格网人口约为 1589.3 人 [E3]，LST 中位数为 51.2°C [E4]。\n有效陆地绿地比例为 0.2 [E5]。`;
    const displayed = presentAgentAnswer(raw, "zh-CN");

    expect(displayed).toContain("当前为证据约束决策模式");
    expect(displayed).toContain("格网 R16-C13");
    expect(displayed).toContain("最大加权贡献项为热危险度");
    expect(displayed).toContain("最大贡献项不代表因果作用");
    expect(displayed).toContain("人口约 1,589 人 [E3]");
    expect(displayed).toContain("绿地比例约 20.0% [E5]");
    expect(displayed).not.toContain("模型服务暂时不可用");
    expect(displayed).not.toContain(gridId);
    expect(displayed).not.toMatch(/\bhazard\b/);
  });

  it("presents the equivalent English answer without failure wording", () => {
    const raw = `The model service is temporarily unavailable. This is a HeatSafe REAL-data summary. Grid ${gridId} has relative risk 90.2 [E1], with hazard as its largest available contribution.\nIts estimated population is 1589.3 [E3], and median LST is 51.2°C [E4].\nGreen fraction over valid land is 0.2 [E5].`;
    const displayed = presentAgentAnswer(raw, "en");

    expect(displayed).toContain("Evidence-grounded decision mode is active");
    expect(displayed).toContain("Grid R16-C13");
    expect(displayed).toContain("largest weighted contribution is heat hazard");
    expect(displayed).toContain("approximately 1,589 people [E3]");
    expect(displayed).toContain("approximately 20.0% [E5]");
    expect(displayed).not.toContain("temporarily unavailable");
  });

  it("keeps scope limitations semantically unchanged", () => {
    const refusal = "当前证据不能支持反事实或干预后的量化风险下降预测。[E1]";
    expect(presentAgentAnswer(refusal, "zh-CN")).toBe(refusal);
  });

  it("localizes internal contribution keys in rendered action answers", () => {
    expect(presentAgentAnswer("排序依据是现有 hazard_contribution_points 加权贡献。", "zh-CN"))
      .toBe("排序依据是现有热危险度加权贡献。");
    expect(presentAgentAnswer("weighted contribution from exposure_contribution_points.", "en"))
      .toBe("weighted contribution from population exposure.");
  });
});
