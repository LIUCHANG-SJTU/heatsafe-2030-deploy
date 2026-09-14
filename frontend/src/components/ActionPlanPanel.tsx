import { BookOpen, Lightbulb, ShieldCheck } from "lucide-react";
import type { ActionCard, ActionEvidenceRef, GridActionPlan } from "../api/types";
import { useI18n } from "../i18n/useI18n";
import type { Locale } from "../i18n/types";
import { formatPopulation } from "../lib/format";

interface ActionPlanPanelProps { plan: GridActionPlan | null; loading?: boolean; error?: string | null }

const metricLabels: Record<Locale, Record<string, string>> = {
  "zh-CN": { hazard_contribution_points: "热危险度加权贡献", exposure_contribution_points: "人口暴露加权贡献", vulnerability_contribution_points: "脆弱性加权贡献", adaptive_deficit_contribution_points: "适应能力缺口加权贡献", lst_median_c: "LST 中位数", population_total: "人口", green_fraction_land: "绿地比例", elderly_share: "老年人 65+", child_share: "儿童 0–14 岁" },
  en: { hazard_contribution_points: "Hazard contribution", exposure_contribution_points: "Exposure contribution", vulnerability_contribution_points: "Vulnerability contribution", adaptive_deficit_contribution_points: "Adaptive capacity gap contribution", lst_median_c: "Median LST", population_total: "Population", green_fraction_land: "Green fraction", elderly_share: "Older adults 65+", child_share: "Children 0–14" },
};

const formatEvidence = (item: ActionEvidenceRef, locale: Locale) => {
  if (typeof item.value !== "number") return String(item.value);
  if (["green_fraction_land", "elderly_share", "child_share"].includes(item.metric)) return `${(item.value * 100).toFixed(1)}%`;
  if (item.metric === "population_total") return formatPopulation(item.value, locale);
  if (item.metric === "lst_median_c") return `${item.value.toFixed(1)}°C`;
  return locale === "zh-CN" ? `${item.value.toFixed(1)} 分` : `${item.value.toFixed(1)} pts`;
};

const organizationLabel = (organization: string) => organization.includes("UN-Habitat") || organization.includes("联合国人居署") ? "UN-Habitat" : organization.includes("World Health Organization") || organization.includes("世界卫生组织") ? "WHO" : organization;

function GuidanceBadges({ card, plan, locale }: { card: ActionCard; plan: GridActionPlan; locale: Locale }) {
  const guidance = card.guidance_ids.map((id) => plan.guidance.find((item) => item.guidance_id === id)).filter((item): item is NonNullable<typeof item> => Boolean(item));
  return <div className="guidance-badges" aria-label={locale === "zh-CN" ? "公开指南来源" : "Public guidance sources"}><BookOpen size={14} aria-hidden="true" />{guidance.map((item) => {
    const organization = locale === "zh-CN" ? item.organization_zh : item.organization_en;
    const title = locale === "zh-CN" ? item.title_zh : item.title_en;
    const section = locale === "zh-CN" ? item.section_zh : item.section_en;
    return <a className="guidance-badge" href={item.url} target="_blank" rel="noreferrer" key={item.guidance_id} title={`${title} · ${section}`}>{organizationLabel(organization)}</a>;
  })}</div>;
}

export function ActionPlanPanel({ plan, loading = false, error = null }: ActionPlanPanelProps) {
  const { locale, t } = useI18n();
  if (loading) return <section id="action-plan" className="action-plan action-state" aria-live="polite" tabIndex={-1}><span className="action-state-dot" />{t("actions.loading")}</section>;
  if (error) return <section id="action-plan" className="action-plan action-state error" role="status" tabIndex={-1}>{t("actions.error")}</section>;
  if (!plan) return null;
  const cards = [...plan.action_cards].sort((a, b) => a.priority_rank - b.priority_rank);
  return <section id="action-plan" className="action-plan" aria-labelledby="action-plan-heading" tabIndex={-1}><div className="action-plan-heading"><div><span className="eyebrow">{t("actions.eyebrow")}</span><h3 id="action-plan-heading">{t("actions.title")}</h3></div><Lightbulb size={19} aria-hidden="true" /></div><div className="action-list">{cards.map((card) => {
    const title = locale === "zh-CN" ? card.title_zh : card.title_en;
    const recommendations = locale === "zh-CN" ? card.recommended_actions_zh : card.recommended_actions_en;
    const why = locale === "zh-CN" ? card.why_zh : card.why_en;
    return <article className={`action-card priority-${card.priority_rank} family-${card.action_family.toLowerCase()}`} key={card.action_family}><header><span>{t("actions.priority", { rank: card.priority_rank })}</span><strong>{t("actions.points", { value: card.signal_points.toFixed(1) })}</strong></header><h4>{title}</h4><div className="action-recommendations-label">{t("actions.recommendations")}</div><ul>{recommendations.map((action) => <li key={action}>{action}</li>)}</ul><div className="action-why"><b>{t("actions.why")}</b><span>{why}</span></div><div className="evidence-chips" aria-label={t("actions.evidence")}>{card.supporting_evidence.map((item) => <span className="evidence-chip" key={`${item.evidence_id}-${item.metric}`} title={`${metricLabels[locale][item.metric] || item.metric}: ${formatEvidence(item, locale)}`}><b>{item.evidence_id}</b>{metricLabels[locale][item.metric] || item.metric}</span>)}</div><GuidanceBadges card={card} plan={plan} locale={locale} /></article>;
  })}</div><div className="action-boundary"><ShieldCheck size={15} aria-hidden="true" /><p>{locale === "zh-CN" ? cards[0]?.limitation_zh : cards[0]?.limitation_en}</p></div></section>;
}
