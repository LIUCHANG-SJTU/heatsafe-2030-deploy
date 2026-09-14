from __future__ import annotations

from typing import Any

from .evidence import EvidenceFact
from .localization import AgentLocale


class DeterministicFallbackResponder:
    def grid_explanation(self, data: dict[str, Any], evidence: list[EvidenceFact], *, locale: AgentLocale = "zh-CN") -> str:
        by_metric = {item.metric: item for item in evidence}
        gid = data.get("grid_id", "selected grid")
        risk = _display(by_metric.get("risk_score"))
        driver = data.get("primary_driver") or data.get("largest_contribution") or "the available components"
        if locale == "en":
            lines = [f"The model service is temporarily unavailable. This is a HeatSafe REAL-data summary. Grid {gid} has relative risk {risk} [{_ref(by_metric.get('risk_score'))}], with {driver} as its largest available contribution."]
        else:
            lines = [f"当前模型服务暂时不可用，以下为 HeatSafe REAL 数据摘要。格网 {gid} 的相对风险为 {risk} [{_ref(by_metric.get('risk_score'))}]，主要贡献项为 {driver}。"]
        if by_metric.get("population_total"):
            if locale == "en":
                lines.append(f"Its estimated population is {_display(by_metric['population_total'])} [{_ref(by_metric['population_total'])}], and median LST is {_display(by_metric.get('lst_median_c'))}°C [{_ref(by_metric.get('lst_median_c'))}].")
            else:
                lines.append(f"该格网人口约为 {_display(by_metric['population_total'])} 人 [{_ref(by_metric['population_total'])}]，LST 中位数为 {_display(by_metric.get('lst_median_c'))}°C [{_ref(by_metric.get('lst_median_c'))}]。")
        if by_metric.get("green_fraction_land"):
            lines.append(
                f"Green fraction over valid land is {_display(by_metric['green_fraction_land'])} [{_ref(by_metric['green_fraction_land'])}]."
                if locale == "en"
                else f"有效陆地绿地比例为 {_display(by_metric['green_fraction_land'])} [{_ref(by_metric['green_fraction_land'])}]。"
            )
        return "\n".join(lines)

    def summary(self, data: dict[str, Any], evidence: list[EvidenceFact], *, locale: AgentLocale = "zh-CN") -> str:
        values = {item.metric: item for item in evidence}
        if locale == "en":
            return (f"The current analysis area contains {_display(values['total_grid_count'])} grids [{_ref(values['total_grid_count'])}], "
                    f"including {_display(values['analyzable_land_grid_count'])} analyzable land grids [{_ref(values['analyzable_land_grid_count'])}] and "
                    f"{_display(values['water_excluded_grid_count'])} excluded water grids [{_ref(values['water_excluded_grid_count'])}]. "
                    f"Estimated population is {_display(values['total_population_est'])} [{_ref(values['total_population_est'])}], and the shared temporal severity score is "
                    f"{_display(values['temporal_severity_score'])} [{_ref(values['temporal_severity_score'])}]. Risk is relative spatial risk within the analysis area "
                    f"[{_ref(values['risk_scope'])}]. Data mode is {values['data_mode'].value} [{_ref(values['data_mode'])}], and model status is "
                    f"{values['model_status'].value} [{_ref(values['model_status'])}].")
        return (f"当前分析区域包含 {_display(values['total_grid_count'])} 个格网 [{_ref(values['total_grid_count'])}]，"
                f"其中可分析陆地 {_display(values['analyzable_land_grid_count'])} 个 [{_ref(values['analyzable_land_grid_count'])}]，"
                f"水域排除 {_display(values['water_excluded_grid_count'])} 个 [{_ref(values['water_excluded_grid_count'])}]。"
                f"估算人口为 {_display(values['total_population_est'])} 人 [{_ref(values['total_population_est'])}]，共享时间热强度为 "
                f"{_display(values['temporal_severity_score'])} [{_ref(values['temporal_severity_score'])}]。风险范围是 AOI 内相对空间风险 "
                f"[{_ref(values['risk_scope'])}]；数据模式为 {values['data_mode'].value} [{_ref(values['data_mode'])}]，模型状态为 "
                f"{values['model_status'].value} [{_ref(values['model_status'])}]。")

    def scope(self, *, locale: AgentLocale = "zh-CN") -> str:
        if locale == "en":
            return "HeatSafe does not simulate counterfactual or future scenarios and does not predict quantified intervention effects. It can provide non-quantified action-priority decision support grounded in the current REAL Evidence."
        return "HeatSafe 当前不支持反事实或未来情景数值模拟，也不预测措施实施后的量化效果。可以基于现有 REAL Evidence 提供非量化的行动优先级决策支持。"


def _id(item: EvidenceFact | None) -> str:
    return (item.evidence_id or "?") if item else "?"


def _ref(item: EvidenceFact | None) -> str:
    return _id(item)


def _display(item: EvidenceFact | None) -> str:
    if item is None or item.value is None:
        return "—"
    if isinstance(item.value, float):
        return f"{item.value:.1f}"
    return str(item.value)
