import type { Locale } from "../i18n/types";
import { contributionMetricLabel, formatGridCode, formatPopulation } from "../lib/format";
import type { AgentEvidence } from "./types";

const GROUNDED_NOTICE: Record<Locale, string> = {
  "zh-CN": "当前为证据约束决策模式。以下回答直接来自 HeatSafe 冻结公开数据与规则化工具链，并附可追溯证据。",
  en: "Evidence-grounded decision mode is active. This answer comes directly from HeatSafe's frozen public data and rule-based tools, with traceable evidence.",
};

const DRIVER_NAMES: Record<Locale, Record<string, string>> = {
  "zh-CN": {
    hazard: "热危险度",
    exposure: "人口暴露",
    vulnerability: "脆弱性",
    adaptive_capacity_deficit: "适应能力缺口",
    "the available components": "现有指标",
  },
  en: {
    hazard: "heat hazard",
    exposure: "population exposure",
    vulnerability: "vulnerability",
    adaptive_capacity_deficit: "adaptive capacity gap",
    "the available components": "the available indicators",
  },
};

function numberValue(value: string): number {
  return Number(value.replaceAll(",", ""));
}

function replaceInternalMetrics(text: string, locale: Locale): string {
  const withoutDuplicateContribution = text
    .replace(
      /现有\s+(hazard|exposure|vulnerability|adaptive_deficit|adaptive_capacity_gap|adaptation_gap)_contribution_points\s+加权贡献/g,
      (_match, metric: string) => `现有${contributionMetricLabel(`${metric}_contribution_points`, "zh-CN")}`,
    )
    .replace(
      /weighted contribution from (hazard|exposure|vulnerability|adaptive_deficit|adaptive_capacity_gap|adaptation_gap)_contribution_points\b/gi,
      (_match, metric: string) => `weighted contribution from ${contributionMetricLabel(metric, "en")}`,
    );
  return withoutDuplicateContribution.replace(
    /\b(?:hazard|exposure|vulnerability|adaptive_deficit|adaptive_capacity_gap|adaptation_gap)_contribution_points\b/g,
    (metric) => contributionMetricLabel(metric, locale),
  );
}

export function presentAgentAnswer(text: string, locale: Locale, evidence: AgentEvidence[] = []): string {
  const greenFractionById = new Map(
    evidence
      .filter((item) => item.metric === "green_fraction_land" && typeof item.value === "number")
      .map((item) => [item.evidence_id, item.value as number]),
  );
  let answer = text
    .replace(
      /^当前模型服务暂时不可用(?:，以下为 HeatSafe REAL 数据摘要。?)?/,
      GROUNDED_NOTICE["zh-CN"],
    )
    .replace(
      /^The model service is temporarily unavailable\.(?: This is a HeatSafe REAL-data summary\.)?/,
      GROUNDED_NOTICE.en,
    )
    .replace(/现有 REAL Evidence\s*/g, "现有可追溯数据证据，")
    .replace(/current REAL Evidence/gi, "current traceable data evidence")
    .replace(/M4B-R-[A-Z0-9]+-G-(R\d+-C\d+)/g, (_match, code: string) => formatGridCode(code));

  answer = answer.replace(/主要贡献项为 ([^。]+)。/g, (_match, driver: string) => {
    const label = DRIVER_NAMES["zh-CN"][driver.trim()] || contributionMetricLabel(driver.trim(), "zh-CN");
    return `最大加权贡献项为${label}。最大贡献项不代表因果作用。`;
  });
  answer = answer.replace(/with ([^.]+) as its largest available contribution\./g, (_match, driver: string) => {
    const label = DRIVER_NAMES.en[driver.trim()] || contributionMetricLabel(driver.trim(), "en");
    return `Its largest weighted contribution is ${label}. The largest contribution does not imply causation.`;
  });

  answer = answer
    .replace(/人口约为?\s*([\d,.]+)\s*人/g, (_match, value: string) => `人口约 ${formatPopulation(numberValue(value), "zh-CN")} 人`)
    .replace(/estimated population is\s*([\d,.]+)/gi, (_match, value: string) => `estimated population is approximately ${formatPopulation(numberValue(value), "en")} people`)
    .replace(/有效陆地绿地比例为\s*(0(?:\.\d+)?|1(?:\.0+)?)\s*\[(E\d+)\]/g, (_match, value: string, evidenceId: string) => {
      const preciseValue = greenFractionById.get(evidenceId) ?? numberValue(value);
      return `有效陆地绿地比例约 ${(preciseValue * 100).toFixed(1)}% [${evidenceId}]`;
    })
    .replace(/Green fraction over valid land is\s*(0(?:\.\d+)?|1(?:\.0+)?)\s*\[(E\d+)\]/gi, (_match, value: string, evidenceId: string) => {
      const preciseValue = greenFractionById.get(evidenceId) ?? numberValue(value);
      return `Green fraction over valid land is approximately ${(preciseValue * 100).toFixed(1)}% [${evidenceId}]`;
    });

  return replaceInternalMetrics(answer, locale);
}
