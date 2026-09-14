import type { FeatureCollection, Polygon } from "geojson";

export type MetricKey =
  | "risk_score"
  | "hazard_score"
  | "exposure_score"
  | "vulnerability_score"
  | "adaptive_capacity_gap"
  | "population_total"
  | "lst_median_c"
  | "green_fraction_land"
  | "water_fraction_grid";

export type Driver = "hazard" | "exposure" | "vulnerability" | "adaptive_capacity_deficit" | null;

export interface DemoSummary {
  demo_id: string;
  api_version: string;
  demo_revision: string;
  qa_contract_version: string;
  data_mode: "REAL" | "MIXED" | "FIXTURE";
  model_status: string;
  risk_scope: string;
  event: Record<string, unknown>;
  aoi: Record<string, any>;
  temporal_context: Record<string, any>;
  methods: Record<string, string>;
  weights: Record<string, number>;
  quality_summary: Record<string, any>;
  summary: {
    total_grid_count: number;
    analyzable_land_grid_count: number;
    water_excluded_grid_count: number;
    total_population_est: number;
    water_excluded_population_fraction: number;
    temporal_severity_score?: number;
    top_10_hotspots: Array<{ grid_id: string; risk_score: number; population_total: number }>;
    [key: string]: any;
  };
}

export interface DemoGridProperties {
  grid_id: string;
  analysis_status: string;
  analysis_reasons: string[];
  ranking_eligible: boolean;
  landsat_quality_flag: string;
  sentinel_quality_flag: string;
  lst_valid_fraction?: number | null;
  sentinel_valid_fraction?: number | null;
  risk_score: number | null;
  risk_percentile_within_aoi: number | null;
  hazard_score: number | null;
  exposure_score: number | null;
  vulnerability_score: number | null;
  adaptive_capacity_score: number | null;
  population_total: number;
  lst_median_c: number | null;
  green_fraction_land: number | null;
  water_fraction_grid: number;
  primary_driver: Driver;
  H: number | null;
  E: number | null;
  V: number | null;
  A: number | null;
}

export type DemoGridFeature = GeoJSON.Feature<Polygon, DemoGridProperties>;
export type DemoGridCollection = FeatureCollection<Polygon, DemoGridProperties>;

export interface DemoGridDetail extends DemoGridProperties {
  row: number;
  column: number;
  geometry: Record<string, any>;
  source_mode: string;
  population_age_0_14: number;
  population_age_65_plus: number;
  elderly_share: number;
  child_share: number;
  vulnerability_share_raw: number;
  ndvi_median_land: number | null;
  green_fraction_grid_legacy: number | null;
  sentinel_valid_fraction: number;
  lst_valid_fraction?: number | null;
  spatial_heat_score: number | null;
  temporal_severity_score: number;
  temporal_context_id: string;
  source_ids: string[];
  hazard_contribution_points: number | null;
  exposure_contribution_points: number | null;
  vulnerability_contribution_points: number | null;
  adaptive_deficit_contribution_points: number | null;
  methods: Record<string, string>;
  quality: Record<string, unknown>;
  provenance: Record<string, unknown>;
  temporal_context: Record<string, unknown> | null;
}

export type ActionFamily =
  | "HEAT_EXPOSURE_MITIGATION"
  | "POPULATION_EXPOSURE_MANAGEMENT"
  | "VULNERABLE_POPULATION_PROTECTION"
  | "ADAPTIVE_CAPACITY_ENHANCEMENT";

export interface ActionGuidanceRef {
  guidance_id: string;
  organization_zh: string;
  organization_en: string;
  title_zh: string;
  title_en: string;
  year: number;
  section_zh: string;
  section_en: string;
  url: string;
}

export interface ActionEvidenceRef {
  evidence_id: string;
  metric: string;
  grid_id: string | null;
  value: unknown;
}

export interface ActionCard {
  priority_rank: number;
  action_family: ActionFamily;
  title_zh: string;
  title_en: string;
  recommended_actions_zh: string[];
  recommended_actions_en: string[];
  why_zh: string;
  why_en: string;
  signal_metric: string;
  signal_points: number;
  supporting_evidence: ActionEvidenceRef[];
  guidance_ids: string[];
  recommendation_status: "DECISION_SUPPORT_HEURISTIC";
  effect_estimate: null;
  limitation_zh: string;
  limitation_en: string;
}

export interface GridActionPlan {
  scope: "grid";
  grid_id: string;
  risk_score: number;
  risk_scope: "RELATIVE_WITHIN_DEMO_AOI";
  action_cards: ActionCard[];
  guidance: ActionGuidanceRef[];
  recommendation_status: "DECISION_SUPPORT_HEURISTIC";
}
