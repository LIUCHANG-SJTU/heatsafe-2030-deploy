import type { Locale } from "../i18n/types";

export const formatPopulation = (value: number | null | undefined, locale: Locale = "zh-CN") => value == null ? "—" : new Intl.NumberFormat(locale === "zh-CN" ? "zh-CN" : "en-US", { maximumFractionDigits: 0 }).format(value);
export const formatScore = (value: number | null | undefined) => value == null ? "—" : value.toFixed(1);
export const formatFraction = (value: number | null | undefined) => value == null ? "—" : value.toFixed(2);
export const formatPercent = (value: number | null | undefined) => value == null ? "—" : `${(value * 100).toFixed(1)}%`;
export const formatTemperature = (value: number | null | undefined) => value == null ? "—" : `${value.toFixed(1)}°C`;
const DRIVER_LABELS: Record<Locale, Record<string, string>> = {
  "zh-CN": {
    hazard: "热危险度主导",
    exposure: "人口暴露主导",
    vulnerability: "脆弱性主导",
    adaptive_capacity_deficit: "适应能力缺口主导",
  },
  en: {
    hazard: "Hazard dominant",
    exposure: "Exposure dominant",
    vulnerability: "Vulnerability dominant",
    adaptive_capacity_deficit: "Adaptive capacity gap dominant",
  },
};
export const driverLabel = (driver: string | null, locale: Locale = "zh-CN") => DRIVER_LABELS[locale][driver || ""] || "—";

const METRIC_LABELS: Record<Locale, Record<string, string>> = {
  "zh-CN": {
    risk_score: "热风险",
    hazard_score: "热危险度",
    exposure_score: "人口暴露",
    vulnerability_score: "脆弱性",
    adaptive_capacity_gap: "适应能力缺口",
    population_total: "人口",
    lst_median_c: "LST 中位数",
    green_fraction_land: "绿地比例",
    water_fraction_grid: "水域比例",
  },
  en: {
    risk_score: "Heat Risk",
    hazard_score: "Hazard",
    exposure_score: "Exposure",
    vulnerability_score: "Vulnerability",
    adaptive_capacity_gap: "Adaptive Capacity Gap",
    population_total: "Population",
    lst_median_c: "Median LST",
    green_fraction_land: "Green Fraction",
    water_fraction_grid: "Water Fraction",
  },
};
export const metricLabel = (metric: string, locale: Locale = "zh-CN") => METRIC_LABELS[locale][metric] || metric;

const EVIDENCE_METRIC_LABELS: Record<Locale, Record<string, string>> = {
  "zh-CN": {
    risk_score: "热风险", risk_scale_max: "风险量表上限", risk_percentile_within_aoi: "风险分位", risk_percentile_percent: "风险分位",
    population_total: "人口", lst_median_c: "LST 中位数", green_fraction_land: "绿地比例", water_fraction_grid: "水域比例",
    hazard_score: "热危险度", exposure_score: "人口暴露", vulnerability_score: "脆弱性", adaptive_capacity_score: "适应能力",
    hazard_contribution_points: "热危险度加权贡献", exposure_contribution_points: "人口暴露加权贡献", vulnerability_contribution_points: "脆弱性加权贡献", adaptive_deficit_contribution_points: "适应能力缺口加权贡献",
    elderly_share: "老年人口占比", child_share: "儿童占比", analysis_status: "分析状态", recommendation_status: "建议状态",
  },
  en: {
    risk_score: "Heat Risk", risk_scale_max: "Risk Scale Maximum", risk_percentile_within_aoi: "Risk Percentile", risk_percentile_percent: "Risk Percentile",
    population_total: "Population", lst_median_c: "Median LST", green_fraction_land: "Green Fraction", water_fraction_grid: "Water Fraction",
    hazard_score: "Hazard", exposure_score: "Exposure", vulnerability_score: "Vulnerability", adaptive_capacity_score: "Adaptive Capacity",
    hazard_contribution_points: "Hazard Contribution", exposure_contribution_points: "Exposure Contribution", vulnerability_contribution_points: "Vulnerability Contribution", adaptive_deficit_contribution_points: "Adaptive Capacity Gap Contribution",
    elderly_share: "Older-adult Share", child_share: "Child Share", analysis_status: "Analysis Status", recommendation_status: "Recommendation Status",
  },
};
export const evidenceMetricLabel = (metric: string, fallback: string, locale: Locale = "zh-CN") => EVIDENCE_METRIC_LABELS[locale][metric] || fallback;

const SOURCE_COMPONENT_LABELS: Record<Locale, Record<string, string>> = {
  "zh-CN": { RISK_MODEL: "风险模型", WORLDPOP: "WorldPop 人口数据", LANDSAT: "Landsat 地表温度", SENTINEL2: "Sentinel-2 地表覆盖", ERA5_LAND: "ERA5-Land 时间背景", ACTION_ENGINE: "行动优先级引擎", DEMO_REPOSITORY: "HeatSafe 数据仓库" },
  en: { RISK_MODEL: "Risk Model", WORLDPOP: "WorldPop Population Data", LANDSAT: "Landsat Surface Temperature", SENTINEL2: "Sentinel-2 Land Cover", ERA5_LAND: "ERA5-Land Temporal Context", ACTION_ENGINE: "Action Priority Engine", DEMO_REPOSITORY: "HeatSafe Data Repository" },
};
export const sourceComponentLabel = (source: string, locale: Locale = "zh-CN") => SOURCE_COMPONENT_LABELS[locale][source] || source;
