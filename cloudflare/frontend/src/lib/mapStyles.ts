import type { ExpressionSpecification } from "maplibre-gl";
import type { MetricKey } from "../api/types";

export const metricProperty = (metric: MetricKey): string => metric === "adaptive_capacity_gap" ? "adaptive_capacity_score" : metric;

export const metricExpression = (metric: MetricKey): ExpressionSpecification => {
  if (metric === "adaptive_capacity_gap") return ["case", ["==", ["get", "adaptive_capacity_score"], null] as any, null, ["-", 1, ["get", "adaptive_capacity_score"]]] as any;
  return ["get", metricProperty(metric)] as ExpressionSpecification;
};

const withExcludedWater = (expression: ExpressionSpecification): ExpressionSpecification => [
  "case",
  ["==", ["get", "analysis_status"], "NON_URBAN_WATER"],
  "#8496aa",
  expression,
] as ExpressionSpecification;

export const fillColorExpression = (metric: MetricKey): ExpressionSpecification => {
  if (metric === "water_fraction_grid") return ["case", [">=", ["get", "water_fraction_grid"], 0.5], "#8496aa", "#d7e5d8"];
  if (metric === "green_fraction_land") return withExcludedWater(["interpolate", ["linear"], ["coalesce", metricExpression(metric), 0], 0, "#f1f5e9", 0.5, "#8dbb76", 1, "#1c6b4b"]);
  if (metric === "population_total") return withExcludedWater(["interpolate", ["linear"], ["coalesce", metricExpression(metric), 0], 0, "#edf0f7", 2000, "#6474a2", 4000, "#18294c"]);
  if (metric === "lst_median_c") return withExcludedWater(["interpolate", ["linear"], ["coalesce", metricExpression(metric), 0], 25, "#fff3b0", 38, "#f97316", 50, "#b91c1c"]);
  if (metric === "risk_score") return withExcludedWater(["interpolate", ["linear"], ["coalesce", metricExpression(metric), 0], 0, "#fff7dc", 50, "#f7c66c", 70, "#ed8b3a", 85, "#d84a35", 100, "#8f1d24"]);
  return withExcludedWater(["interpolate", ["linear"], ["coalesce", metricExpression(metric), 0], 0, "#fef3a2", 0.5, "#f97316", 1, "#c51f25"]);
};

export const RISK_LAYER = "risk-grid-fill";
