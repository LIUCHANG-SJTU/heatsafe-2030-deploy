import type { ReactNode } from "react";
import { ArrowDown } from "lucide-react";
import type { DemoGridDetail, GridActionPlan } from "../api/types";
import { driverLabel, formatFraction, formatPercent, formatPopulation, formatScore, formatTemperature } from "../lib/format";
import { ContributionBars } from "./ContributionBars";
import { ActionPlanPanel } from "./ActionPlanPanel";
import { useI18n } from "../i18n/useI18n";

const Metric = ({ label, value }: { label: string; value: ReactNode }) => <div className="raw-metric"><span>{label}</span><strong>{value}</strong></div>;

export function SelectedGridPanel({ grid, loading, actionPlan, actionLoading, actionError }: { grid: DemoGridDetail | null; loading?: boolean; actionPlan?: GridActionPlan | null; actionLoading?: boolean; actionError?: string | null }) {
  const { locale, t } = useI18n();
  if (loading) return <aside className="panel selected-panel"><div className="skeleton large" /><div className="skeleton" /><div className="skeleton" /></aside>;
  if (!grid) return <aside className="panel selected-panel empty"><span className="eyebrow">{t("grid.selected")}</span><h2>{t("grid.selectTitle")}</h2><p>{t("grid.selectHelp")}</p></aside>;
  const water = grid.analysis_status === "NON_URBAN_WATER";
  const showActionShortcut = !water && Boolean(actionPlan || actionLoading || actionError);
  const goToActions = () => {
    const actionSection = document.getElementById("action-plan");
    actionSection?.scrollIntoView({ behavior: "smooth", block: "start" });
    actionSection?.focus({ preventScroll: true });
  };
  return <aside className="panel selected-panel" aria-live="polite">
    <div className="panel-kicker"><span className="eyebrow">{t("grid.selected")}</span><span className={`status-pill ${water ? "water" : "land"}`}>{water ? t("grid.excludedWater") : t("grid.analyzableLand")}</span></div>
    <h2 className="grid-id">{grid.grid_id}</h2>
    <div className="selected-risk"><div><span>{t("grid.relativeRisk")}</span><strong>{water ? "N/A" : formatScore(grid.risk_score)}</strong></div><div className="percentile"><span>{t("grid.percentile")}</span><strong>{formatPercent(grid.risk_percentile_within_aoi)}</strong></div></div>
    <div className="driver"><span>{t("grid.primaryDriver")}</span><strong>{driverLabel(grid.primary_driver, locale)}</strong></div>
    {showActionShortcut && <button className="action-jump" type="button" onClick={goToActions}>{t("actions.viewPriority")}<ArrowDown size={16} aria-hidden="true" /></button>}
    <div className="section-heading compact"><span>{t("grid.context")}</span></div>
    <div className="raw-grid context-grid"><Metric label={t("grid.population")} value={formatPopulation(grid.population_total, locale)} /><Metric label={t("grid.lst")} value={formatTemperature(grid.lst_median_c)} /><Metric label={t("grid.green")} value={formatPercent(grid.green_fraction_land)} /><Metric label={t("grid.vulnerableCue")} value={`${t("grid.elderly")} ${formatPercent(grid.elderly_share)} · ${t("grid.children")} ${formatPercent(grid.child_share)}`} /></div>
    {!water && <><div className="section-heading"><span>{t("grid.decomposition")}</span><small>{t("grid.points")}</small></div><ContributionBars values={[{ label: t("grid.hazard"), value: grid.hazard_contribution_points, color: "#e0523f" }, { label: t("grid.exposure"), value: grid.exposure_contribution_points, color: "#d8902f" }, { label: t("grid.vulnerability"), value: grid.vulnerability_contribution_points, color: "#8666a7" }, { label: t("grid.adaptiveDeficit"), value: grid.adaptive_deficit_contribution_points, color: "#2e8764" }]} /></>}
    {!water && <ActionPlanPanel plan={actionPlan || null} loading={actionLoading} error={actionError} />}
    {water && <div className="water-note">{t("grid.waterNote")}</div>}
    <details className="technical-details"><summary>{t("grid.technicalDetails")}</summary><div className="quality-grid"><Metric label={t("grid.ndvi")} value={formatFraction(grid.ndvi_median_land)} /><Metric label={t("grid.water")} value={formatPercent(grid.water_fraction_grid)} /><Metric label={t("grid.landsatQuality")} value={grid.landsat_quality_flag === "HIGH" ? t("grid.qualityHigh") : grid.landsat_quality_flag} /><Metric label={t("grid.landsatValid")} value={formatPercent(grid.lst_valid_fraction)} /><Metric label={t("grid.sentinelQuality")} value={grid.sentinel_quality_flag === "HIGH" ? t("grid.qualityHigh") : grid.sentinel_quality_flag} /><Metric label={t("grid.sentinelValid")} value={formatPercent(grid.sentinel_valid_fraction)} /><Metric label={t("grid.analysisReasons")} value={grid.analysis_reasons.length ? grid.analysis_reasons.map((reason) => reason === "WATER_EXCLUDED" ? t("grid.waterExcludedReason") : reason).join(", ") : "—"} /></div></details>
  </aside>;
}
