import { formatScore } from "../lib/format";
import { useI18n } from "../i18n/useI18n";

export function ContributionBars({ values }: { values: Array<{ label: string; value: number | null; color: string }> }) {
  const { locale } = useI18n();
  return <div className="contributions">{values.map((item) => <div className="contribution" key={item.label}><div className="contribution-label"><span>{item.label}</span><strong>{formatScore(item.value)} {locale === "zh-CN" ? "分" : "pts"}</strong></div><div className="bar-track"><div className="bar-fill" style={{ width: `${Math.min(100, ((item.value || 0) / 40) * 100)}%`, background: item.color }} /></div></div>)}</div>;
}
