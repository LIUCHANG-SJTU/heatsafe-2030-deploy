import { useMemo, useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Bot, Download, ExternalLink, Layers3, Menu, X } from "lucide-react";
import type { MetricKey } from "./api/types";
import { useDemo, useDemoGrids, useGridActions, useGridDetail } from "./hooks/useDemo";
import { formatGridLabel, formatPercent, formatPopulation, formatScore, driverLabel } from "./lib/format";
import { MapView } from "./components/MapView";
import { SelectedGridPanel } from "./components/SelectedGridPanel";
import { AgentDrawer } from "./agent/AgentDrawer";
import type { AgentMapAction } from "./agent/types";
import { I18nProvider } from "./i18n/I18nProvider";
import { useI18n } from "./i18n/useI18n";
import "./styles/globals.css";

const queryClient = new QueryClient();
const layers: MetricKey[] = ["risk_score", "hazard_score", "exposure_score", "vulnerability_score", "adaptive_capacity_gap", "population_total", "lst_median_c", "green_fraction_land", "water_fraction_grid"];

function Dashboard() {
  const { locale, setLocale, t } = useI18n();
  const demo = useDemo(); const grids = useDemoGrids();
  const [metric, setMetric] = useState<MetricKey>("risk_score"); const [selected, setSelected] = useState<string | null>(null); const [navOpen, setNavOpen] = useState(false); const [agentOpen, setAgentOpen] = useState(false); const [agentHighlights, setAgentHighlights] = useState<string[]>([]);
  const firstHotspot = demo.data?.summary.top_10_hotspots[0]?.grid_id || null;
  const selectedId = selected || firstHotspot;
  const detail = useGridDetail(selectedId);
  const gridActions = useGridActions(selectedId, detail.data?.analysis_status === "ANALYZABLE_LAND");
  const hotspots = useMemo(() => (demo.data?.summary.top_10_hotspots || []).map((hotspot) => ({
    ...hotspot,
    feature: grids.data?.features.find((feature) => feature.properties.grid_id === hotspot.grid_id),
  })), [demo.data, grids.data]);
  const exportGeoJson = () => { if (!grids.data) return; const blob = new Blob([JSON.stringify(grids.data)], { type: "application/geo+json" }); const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = "heatsafe_hangzhou_analysis_grids.geojson"; link.click(); URL.revokeObjectURL(url); };
  const handleAgentMapAction = (action: AgentMapAction) => { if (action.action === "select_grid" && action.grid_ids[0]) setSelected(action.grid_ids[0]); if (["highlight_grids", "focus_grids"].includes(action.action)) setAgentHighlights(action.grid_ids); if (action.action === "suggest_layer" && action.layer) setMetric(action.layer as MetricKey); };
  if (demo.isError || grids.isError) return <main className="app-shell"><div className="error-screen"><span className="eyebrow">HeatSafe 2030</span><h1>{t("errors.demoTitle")}</h1><p>{t("errors.demoBody")}</p></div></main>;
  const summary = demo.data?.summary;
  const kpis = [
    [t("kpi.totalGrids"), summary?.total_grid_count, t("kpi.totalGridsSub")],
    [t("kpi.land"), summary?.analyzable_land_grid_count, t("kpi.landSub")],
    [t("kpi.water"), summary?.water_excluded_grid_count, t("kpi.waterSub", { value: formatPercent(summary?.water_excluded_population_fraction) })],
    [t("kpi.population"), formatPopulation(summary?.total_population_est, locale), t("kpi.populationSub")],
    [t("kpi.riskP90"), summary?.risk_p90 == null ? "—" : formatScore(summary.risk_p90), t("kpi.riskP90Sub")],
    [t("kpi.temporal"), demo.data?.temporal_context?.temporal_severity_score?.toFixed(4) || "—", t("kpi.temporalSub")],
  ];
  return <main className="app-shell"><header className="topbar"><div className="brand"><div className="brand-mark">HS</div><div><h1>HeatSafe 2030</h1><p>{t("brand.subtitle")}</p></div></div><nav className={navOpen ? "mobile-nav open" : "mobile-nav"}>{[["overview", "nav.overview"], ["map", "nav.map"], ["hotspots", "nav.hotspots"], ["drivers", "nav.drivers"], ["methodology", "nav.methodology"]].map(([id, key]) => <a href={`#${id}`} key={id} onClick={() => setNavOpen(false)}>{t(key as Parameters<typeof t>[0])}</a>)}</nav><div className="top-actions"><span className="badge real">{t("status.realData")}</span><span className="badge dark">{t("status.hangzhouDemo")}</span><div className="locale-switch" role="group" aria-label={t("aria.language")}><button aria-pressed={locale === "zh-CN"} onClick={() => setLocale("zh-CN")}>{t("language.zh")}</button><button aria-pressed={locale === "en"} onClick={() => setLocale("en")}>{t("language.en")}</button></div><button className="icon-button agent-open-button" aria-label={t("aria.openAgent")} title={t("aria.openAgent")} onClick={() => setAgentOpen(true)}><Bot size={18} /><span className="agent-entry-label">{t("agent.entry")}</span></button><button className="icon-button menu-button" aria-label={t("aria.toggleNav")} onClick={() => setNavOpen(!navOpen)}>{navOpen ? <X size={20} /> : <Menu size={20} />}</button></div></header>
    <div className="content"><section id="overview" className="hero"><div><span className="eyebrow">{t("hero.eyebrow")}</span><h2 aria-label={t("hero.slogan")}>{t("hero.titleBefore")}<em>{t("hero.titleEmphasis")}</em>{t("hero.titleAfter")}</h2><p>{t("hero.description")}</p></div><div className="hero-meta"><span>{t("hero.event")}</span><strong>{String(demo.data?.aoi?.event?.date || demo.data?.event?.acquisition_datetime || "—").slice(0, 10)}</strong><small>{t("hero.scope")}</small></div></section>
      <section className="kpi-row">{kpis.map(([label, value, sub]) => <div className="kpi" key={String(label)}><span>{label}</span><strong>{value ?? "—"}</strong><small>{sub}</small></div>)}</section>
      <section id="map" className="map-section"><div className="section-title"><div><span className="eyebrow">{t("map.eyebrow")}</span><h2>{t("map.title")}</h2></div><div className="map-actions"><button className="outline-button" onClick={exportGeoJson} disabled={!grids.data}><Download size={16} />{t("map.export")}</button><span className="api-status"><span />{t("status.realData")}</span></div></div><div className="map-layout"><div className="map-frame">{grids.data ? <MapView grids={grids.data} metric={metric} selectedId={selectedId} agentHighlightIds={agentHighlights} onSelect={setSelected} /> : <div className="loading-map">{t("map.loading", { count: 400 })}</div>}<div className="layer-control"><div className="layer-header"><Layers3 size={16} /><strong>{t("map.layerControl")}</strong></div>{layers.map((layer) => <button key={layer} aria-pressed={metric === layer} className={metric === layer ? "active" : ""} onClick={() => setMetric(layer)}>{t(`layers.${layer}` as Parameters<typeof t>[0])}</button>)}<MapLegend metric={metric} /></div></div><SelectedGridPanel grid={detail.data || null} loading={detail.isLoading && Boolean(selectedId)} actionPlan={gridActions.data || null} actionLoading={gridActions.isLoading && detail.data?.analysis_status === "ANALYZABLE_LAND"} actionError={gridActions.error instanceof Error ? gridActions.error.message : null} /></div></section>
      <section id="hotspots" className="section-block"><div className="section-title"><div><span className="eyebrow">{t("hotspots.eyebrow")}</span><h2>{t("hotspots.title")}</h2></div><span className="preview-note">{t("hotspots.live")}</span></div><div className="hotspot-list">{hotspots.map((hotspot, index) => <button className={`hotspot-row ${index < 3 ? "top-three" : ""} ${selectedId === hotspot.grid_id ? "selected" : ""}`} key={hotspot.grid_id} title={hotspot.grid_id} onClick={() => setSelected(hotspot.grid_id)}><span className="rank">{String(index + 1).padStart(2, "0")}</span><span className="hotspot-id">{formatGridLabel(hotspot.grid_id, locale)}<small>{driverLabel(hotspot.feature?.properties.primary_driver || null, locale)} · {t("hotspots.inspect")}</small></span><span className="hotspot-pop">{formatPopulation(hotspot.population_total, locale)}<small>{t("hotspots.population")}</small></span><span className="hotspot-risk">{formatScore(hotspot.risk_score)}<small>{hotspot.feature?.properties.risk_percentile_within_aoi == null ? t("hotspots.risk") : t("hotspots.percentile", { value: formatPercent(hotspot.feature.properties.risk_percentile_within_aoi) })}</small></span><ExternalLink size={16} /></button>)}</div></section>
      <section id="drivers" className="section-block driver-section"><div className="section-title"><div><span className="eyebrow">{t("drivers.eyebrow")}</span><h2>{t("drivers.title")}</h2></div></div><div className="formula-layout"><div className="formula-card"><div className="formula">{t("drivers.formulaRisk")} <span>=</span> <b>0.40</b> {t("drivers.formulaHazard")} <span>+</span> <b>0.25</b> {t("drivers.formulaExposure")} <span>+</span> <b>0.20</b> {t("drivers.formulaVulnerability")} <span>+</span> <b>0.15</b> {t("drivers.formulaAdaptive")}</div><p>{t("drivers.formulaNote")}</p></div><div className="driver-explanations"><div><b>{t("grid.hazard")}</b><span>{t("drivers.hazard")}</span></div><div><b>{t("grid.exposure")}</b><span>{t("drivers.exposure")}</span></div><div><b>{t("grid.vulnerability")}</b><span>{t("drivers.vulnerability")}</span></div><div><b>{t("grid.adaptiveDeficit")}</b><span>{t("drivers.adaptive")}</span></div></div></div></section>
      <section id="methodology" className="section-block methodology"><div className="section-title"><div><span className="eyebrow">{t("methodology.eyebrow")}</span><h2>{t("methodology.title")}</h2></div></div><div className="source-grid"><Source title="WorldPop 2026" role={t("methodology.worldpopRole")} detail={t("methodology.worldpopDetail")} /><Source title="Landsat 9" role={t("methodology.landsatRole")} detail={t("methodology.landsatDetail")} /><Source title="Sentinel-2" role={t("methodology.sentinelRole")} detail={t("methodology.sentinelDetail")} /><Source title="ERA5-Land" role={t("methodology.eraRole")} detail={t("methodology.eraDetail")} /></div><div className="method-footer"><span>{t("methodology.dataMode")} <b>{t("methodology.public")}</b></span><span>{t("methodology.qa")} <b>{t("methodology.pass")}</b></span><span>{t("methodology.hash")} <b>{t("methodology.traceable")}</b></span><span>{t("methodology.cache")} <b>{t("methodology.reproducible")}</b></span></div></section>
    </div><footer><span>© 2026 HeatSafe 2030 · {t("footer.demo")}</span><span>{t("footer.revision")}</span><span><a href="#methodology">{t("footer.methodology")}</a><a href="#methodology">{t("footer.provenance")}</a><a href="#drivers">{t("footer.limitations")}</a></span></footer><AgentDrawer open={agentOpen} onClose={() => setAgentOpen(false)} selectedGridId={selectedId} activeLayer={metric} onMapAction={handleAgentMapAction} />
  </main>;
}

function MapLegend({ metric }: { metric: MetricKey }) {
  const { t } = useI18n();
  const normalized = ["hazard_score", "exposure_score", "vulnerability_score", "adaptive_capacity_gap"].includes(metric);
  const labels = metric === "risk_score" ? ["0", "50", "100"] : normalized ? ["0", "0.5", "1"] : metric === "population_total" ? ["0", "2,000", "4,000"] : metric === "lst_median_c" ? ["25", "38", "50"] : ["0", "50%", "100%"];
  const description = metric === "risk_score" ? t("map.legendRisk") : normalized ? t("map.legendNormalized") : metric === "population_total" ? t("map.legendPopulation") : metric === "lst_median_c" ? t("map.legendTemperature") : t("map.legendFraction");
  return <div className={`legend legend-${metric}`}><span className="legend-title">{description}</span><i className="risk-swatch" /><div className="legend-scale"><span>{labels[0]}</span><span>{labels[1]}</span><span>{labels[2]}</span></div><div className="legend-note"><b className="water-dot" />{t("map.waterExcluded")}</div></div>;
}

function Source({ title, role, detail }: { title: string; role: string; detail: string }) { return <article className="source-card"><span className="source-dot" /><h3>{title}</h3><b>{role}</b><p>{detail}</p></article>; }
export default function App() { return <I18nProvider><QueryClientProvider client={queryClient}><Dashboard /></QueryClientProvider></I18nProvider>; }
