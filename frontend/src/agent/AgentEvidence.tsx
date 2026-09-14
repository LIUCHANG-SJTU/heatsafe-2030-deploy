import type { AgentEvidence } from "./types";
import { evidenceMetricLabel, formatFraction, formatPercent, formatPopulation, formatScore, formatTemperature, sourceComponentLabel } from "../lib/format";
import { useI18n } from "../i18n/useI18n";
import type { Locale } from "../i18n/types";

function valueLabel(item: AgentEvidence, locale: Locale): string {
  if (item.value == null) return "—";
  if (item.metric === "population_total" || item.unit === "people") return formatPopulation(Number(item.value), locale);
  if (item.metric === "risk_score" || item.unit === "/100" || item.unit === "points") return formatScore(Number(item.value));
  if (item.metric === "lst_median_c" || item.unit === "°C") return formatTemperature(Number(item.value));
  if (item.metric === "risk_percentile_within_aoi") return formatPercent(Number(item.value));
  if (item.metric === "risk_percentile_percent" || item.unit === "%") return `${Number(item.value).toFixed(1)}%`;
  if (typeof item.value === "number" && item.value >= 0 && item.value <= 1) return formatFraction(Number(item.value));
  return String(item.value);
}

export function evidenceIdsInText(text: string): string[] {
  return [...new Set([...text.matchAll(/\[(E\d+)\]/g)].map((match) => match[1]))];
}

export function AgentEvidence({ items, citedEvidenceIds = [], onGridClick }: { items: AgentEvidence[]; citedEvidenceIds?: string[]; onGridClick: (gridId: string) => void }) {
  const { locale, t } = useI18n();
  if (!items.length) return null;
  const cited = new Set(citedEvidenceIds);
  const citedItems = items.filter((item) => cited.has(item.evidence_id));
  const uncitedItems = items.filter((item) => !cited.has(item.evidence_id));
  const visibleItems = [...citedItems, ...uncitedItems.slice(0, Math.max(0, 12 - citedItems.length))];
  return <div className="agent-evidence"><div className="agent-evidence-title">{t("evidence.title")}</div><div className="agent-evidence-grid">{visibleItems.map((item) => <button className="agent-evidence-card" key={item.evidence_id} onClick={() => item.grid_id && onGridClick(item.grid_id)} disabled={!item.grid_id} title={item.grid_id ? t("evidence.gridAction") : undefined}><span>{evidenceMetricLabel(item.metric, item.label, locale)} <small>[{item.evidence_id}]</small></span><strong>{valueLabel(item, locale)}</strong><em>{sourceComponentLabel(item.source_component, locale)}</em></button>)}</div></div>;
}
