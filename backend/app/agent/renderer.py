from __future__ import annotations

from typing import Any

from .evidence import EvidenceFact, ToolResult
from .localization import AgentLocale
from .semantic_contract import CompareMode, compare_mode, grid_context_required, hotspot_population_max_requested


RENDERING_SOURCE = "DETERMINISTIC_GROUNDED_RENDERER"


class DeterministicGroundedRenderer:
    """Render structured tool results using only their assigned Evidence facts."""

    structured_tools = {"explain_risk", "inspect_grid", "compare_grids", "query_grids", "list_hotspots", "get_demo_summary", "get_methodology", "recommend_actions"}

    def can_render(self, result: ToolResult, user_text: str) -> bool:
        if result.tool_name not in self.structured_tools:
            return False
        if result.tool_name == "list_hotspots" and _is_compare_request(user_text) and compare_mode(user_text) != CompareMode.SET:
            return False
        return True

    def render(
        self,
        result: ToolResult,
        user_text: str = "",
        selected_grid_id: str | None = None,
        *,
        locale: AgentLocale = "zh-CN",
    ) -> str:
        if locale == "en":
            return _render_english(result, user_text, selected_grid_id)
        if result.tool_name == "explain_risk":
            return self._explain(result)
        if result.tool_name == "inspect_grid":
            return self._inspect(result)
        if result.tool_name == "compare_grids":
            return self._compare(result, user_text)
        if result.tool_name == "query_grids":
            return self._query(result)
        if result.tool_name == "list_hotspots":
            if hotspot_population_max_requested(user_text) or (
                compare_mode(user_text) == CompareMode.SET and _is_compare_request(user_text)
            ):
                return self._set_population_comparison(result)
            return self._hotspots(result)
        if result.tool_name == "get_demo_summary":
            return self._summary(result, user_text, selected_grid_id)
        if result.tool_name == "get_methodology":
            return self._methodology(result)
        if result.tool_name == "recommend_actions":
            return self._actions(result)
        raise ValueError(f"structured renderer does not support: {result.tool_name}")

    @staticmethod
    def _explain(result: ToolResult) -> str:
        data = result.data if isinstance(result.data, dict) else {}
        grid_id = data.get("grid_id")
        if not isinstance(grid_id, str) or not grid_id:
            raise ValueError("explain renderer requires a grid ID")

        facts = result.evidence
        risk = _optional_numeric_fact(facts, "risk_score", grid_id)
        scale = _optional_numeric_fact(facts, "risk_scale_max")
        if risk is None or scale is None:
            water = _water_explanation(result)
            if water is not None:
                return water
            return (
                f"格网 {grid_id} 当前没有可用的分析区域内相对风险分数，无法进行四项加权贡献解释。\n\n"
                "HeatSafe 不会为缺失指标生成替代数值。"
            )

        percentile = _optional_numeric_fact(facts, "risk_percentile_percent", grid_id)
        dominant = _fact(facts, "dominant_weighted_contribution", grid_id)
        contribution_specs = (
            ("hazard_contribution_points", "Hazard", "hazard"),
            ("exposure_contribution_points", "Exposure", "exposure"),
            ("vulnerability_contribution_points", "Vulnerability", "vulnerability"),
            ("adaptive_deficit_contribution_points", "Adaptive deficit", "adaptive_capacity_deficit"),
        )
        contributions = [
            (label, key, item)
            for metric, label, key in contribution_specs
            if (item := _optional_numeric_fact(facts, metric, grid_id)) is not None
        ]
        dominant_label = next((label for label, key, _ in contributions if key == dominant.value), str(dominant.value))

        parts = [
            f"格网 {grid_id} 的分析区域内相对风险为 {_decimal(risk.value, 1)} / {_integer(scale.value)} "
            f"[{risk.evidence_id}] [{scale.evidence_id}]。"
        ]
        if percentile is not None:
            parts.append(f"风险分位为 {_decimal(percentile.value, 1)}% [{percentile.evidence_id}]。")
        if contributions:
            rendered = []
            for label, key, item in contributions:
                qualifier = f"{label} 为最大加权贡献项 [{dominant.evidence_id}]，贡献" if key == dominant.value else f"{label} 为"
                rendered.append(f"{qualifier} {_decimal(item.value, 1)} 分 [{item.evidence_id}]")
            parts.append("当前四项加权贡献中，" + "；".join(rendered) + "。")

        observations = []
        observation_specs = (
            ("lst_median_c", "LST 中位数", lambda value: f"{_decimal(value, 1)}°C"),
            ("population_total", "人口约", lambda value: f"{_grouped(value)} 人"),
            ("green_fraction_land", "绿地比例", _percent),
            ("elderly_share", "老年人口占比", _percent),
            ("child_share", "儿童占比", _percent),
        )
        for metric, label, formatter in observation_specs:
            item = _optional_numeric_fact(facts, metric, grid_id)
            if item is not None:
                observations.append(f"{label} {formatter(item.value)} [{item.evidence_id}]")
        if observations:
            parts.append("与这些风险构成对应的观测指标包括：" + "，".join(observations) + "。")

        parts.append(
            f"因此，在当前分析区域的相对评分框架下，该格网的高风险主要体现为 {dominant_label} 加权贡献为四项中的最大项，"
            "并与其他加权贡献共同构成当前风险分数。"
        )
        parts.append("该风险分数仅用于当前分析区域内的相对优先级排序，不代表城市级绝对风险、个体健康概率或死亡概率。")
        return "\n\n".join(parts)

    @staticmethod
    def _inspect(result: ToolResult) -> str:
        data = result.data if isinstance(result.data, dict) else {}
        grid_id = data.get("grid_id")
        if not isinstance(grid_id, str) or not grid_id:
            raise ValueError("inspect renderer requires a grid ID")

        facts = result.evidence
        lines = [f"格网 {grid_id}"]

        water = _water_explanation(result)
        if water is not None:
            return water

        risk = _optional_numeric_fact(facts, "risk_score", grid_id)
        scale = _optional_numeric_fact(facts, "risk_scale_max")
        if risk is not None and scale is not None:
            lines.append(
                f"分析区域内相对风险：{_decimal(risk.value, 1)} / {_integer(scale.value)} "
                f"[{risk.evidence_id}] [{scale.evidence_id}]。"
            )

        percentile = _optional_numeric_fact(facts, "risk_percentile_percent", grid_id)
        if percentile is not None:
            lines.append(f"风险分位：{_decimal(percentile.value, 1)}% [{percentile.evidence_id}]。")

        metrics = (
            ("population_total", "人口", lambda value: f"{_grouped(value)} 人"),
            ("lst_median_c", "LST 中位数", lambda value: f"{_decimal(value, 1)}°C"),
            ("green_fraction_land", "绿地比例", _percent),
            ("water_fraction_grid", "水体比例", _percent),
            ("elderly_share", "老年人口占比", _percent),
            ("child_share", "儿童占比", _percent),
        )
        for metric, label, formatter in metrics:
            item = _optional_numeric_fact(facts, metric, grid_id)
            if item is not None:
                lines.append(f"{label}：{formatter(item.value)} [{item.evidence_id}]。")

        quality_metrics = (
            ("landsat_quality_flag", "Landsat 质量"),
            ("sentinel_quality_flag", "Sentinel 质量"),
        )
        for metric, label in quality_metrics:
            item = _optional_metric_fact(facts, metric, grid_id)
            if item is not None and item.value is not None:
                lines.append(f"{label}：{item.value} [{item.evidence_id}]。")

        contributions = (
            ("hazard_contribution_points", "Hazard"),
            ("exposure_contribution_points", "Exposure"),
            ("vulnerability_contribution_points", "Vulnerability"),
            ("adaptive_deficit_contribution_points", "Adaptive deficit"),
        )
        contribution_parts = []
        for metric, label in contributions:
            item = _optional_numeric_fact(facts, metric, grid_id)
            if item is not None:
                contribution_parts.append(f"{label} {_decimal(item.value, 1)} 分 [{item.evidence_id}]")
        if contribution_parts:
            lines.append("风险构成：" + "；".join(contribution_parts) + "。")

        lines.append("以上指标用于当前分析区域内的相对比较，不代表绝对健康或死亡风险。")
        return "\n\n".join(lines)

    @staticmethod
    def _compare(result: ToolResult, user_text: str) -> str:
        data = result.data if isinstance(result.data, dict) else {}
        grids = data.get("grids", [])
        if compare_mode(user_text) == CompareMode.SET:
            return DeterministicGroundedRenderer._set_population_comparison(result)
        if len(grids) != 2:
            raise ValueError("compare renderer requires exactly two grids")
        current, peer = grids
        facts = result.evidence
        current_risk = _fact(facts, "risk_score", current["grid_id"])
        peer_risk = _fact(facts, "risk_score", peer["grid_id"])
        scale = _fact(facts, "risk_scale_max")
        lines = [
            (
                f"当前选择格网 {current['grid_id']} 的分析区域内相对风险为 {_decimal(current_risk.value, 1)} / {_integer(scale.value)} "
                f"[{current_risk.evidence_id}] [{scale.evidence_id}]；风险排名第二格网 {peer['grid_id']} 为 {_decimal(peer_risk.value, 1)} / {_integer(scale.value)} "
                f"[{peer_risk.evidence_id}] [{scale.evidence_id}]。"
            )
        ]
        labels = (
            ("risk_delta", "风险分差", lambda value: f"{_signed(value, 1)} 分"),
            ("hazard_delta", "危害评分差", lambda value: _signed(value, 2)),
            ("exposure_score_delta", "暴露评分差", lambda value: _signed(value, 2)),
            ("population_delta", "人口差", lambda value: f"{_signed_integer(value)} 人"),
            ("lst_delta", "LST 差", lambda value: f"{_signed(value, 1)}°C"),
            ("green_delta", "绿地比例差", lambda value: _signed_percent(value)),
        )
        differences = []
        for metric, label, formatter in labels:
            item = _fact(facts, metric, peer["grid_id"])
            differences.append(f"{label} {formatter(item.value)} [{item.evidence_id}]")
        lines.append("第二名相对当前网格的主要差异：" + "；".join(differences) + "。")
        lines.append("以上均为当前分析区域内的相对比较，不代表绝对健康或死亡风险。")
        return "\n\n".join(lines)

    @staticmethod
    def _set_population_comparison(result: ToolResult) -> str:
        data = result.data if isinstance(result.data, dict) else {}
        grids = data.get("grids", []) if result.tool_name == "compare_grids" else result.data
        if not isinstance(grids, list) or len(grids) < 2:
            raise ValueError("set comparison requires at least two grids")
        populations: list[tuple[dict[str, Any], EvidenceFact]] = []
        for grid in grids:
            if not isinstance(grid, dict) or not isinstance(grid.get("grid_id"), str):
                raise ValueError("set comparison contains an invalid grid")
            populations.append((grid, _fact(result.evidence, "population_total", grid["grid_id"])))
        maximum_value = max(float(item[1].value) for item in populations)
        maxima = [item for item in populations if float(item[1].value) == maximum_value]
        lines = ["热点人口比较："]
        for grid, population in populations:
            lines.append(f"• 格网 {grid['grid_id']}：人口约 {_grouped(population.value)} 人 [{population.evidence_id}]。")
        if len(maxima) == 1:
            maximum_grid, maximum_fact = maxima[0]
            lines.append(
                f"在当前返回的高风险热点集合中，人口最多的是格网 {maximum_grid['grid_id']}，"
                f"人口约 {_grouped(maximum_fact.value)} 人 [{maximum_fact.evidence_id}]。"
            )
        else:
            tied = "、".join(
                f"格网 {grid['grid_id']} [{population.evidence_id}]"
                for grid, population in maxima
            )
            lines.append(
                f"在当前返回的高风险热点集合中，{tied} 并列人口最多，"
                f"均约 {_grouped(maxima[0][1].value)} 人 [{maxima[0][1].evidence_id}]。"
            )
        lines.append("该结论仅针对当前返回的热点集合，不表示杭州市或其他区域的人口最大格网。")
        return "\n".join(lines)

    @staticmethod
    def _actions(result: ToolResult) -> str:
        data = result.data if isinstance(result.data, dict) else {}
        if data.get("scope") == "hotspots":
            return DeterministicGroundedRenderer._hotspot_actions(result)
        grid_id = data.get("grid_id")
        cards = data.get("action_cards")
        if not isinstance(grid_id, str) or not isinstance(cards, list) or not cards:
            raise ValueError("grid action renderer requires an action plan")
        facts = result.evidence
        lines = [f"格网 {grid_id} 的行动优先级建议如下："]
        for card in cards:
            rank = _fact_value(facts, "action_priority_rank", card["priority_rank"], grid_id)
            family = _fact_value(facts, "action_family", card["action_family"], grid_id)
            signal = _fact_value(facts, "action_signal_points", card["signal_points"], grid_id)
            lines.extend([
                f"Priority {_integer(rank.value)} · {card['title_zh']} [{rank.evidence_id}] [{family.evidence_id}]",
                "建议：",
                *[f"• {action}" for action in card["recommended_actions_zh"]],
                "依据：",
                f"{_action_signal_label(card['signal_metric'])}加权贡献 {_decimal(signal.value, 1)} 分 [{signal.evidence_id}]。",
            ])
            for metric in _action_context_metrics(card["action_family"]):
                item = _optional_numeric_fact(facts, metric, grid_id)
                if item is not None:
                    lines.append(_action_context_value(metric, item))
            guidance = [
                item for item in facts
                if item.metric == "action_guidance_ref"
                and item.grid_id == grid_id
                and item.value in card["guidance_ids"]
            ]
            if guidance:
                lines.append("行动类别参考公开 WHO / UN-Habitat 城市热治理 guidance " + " ".join(f"[{item.evidence_id}]" for item in guidance) + "。")
            lines.append("")
        status = _fact(facts, "recommendation_status", grid_id)
        lines.append(f"建议状态：DECISION_SUPPORT_HEURISTIC [{status.evidence_id}]。")
        lines.append("这些建议用于基于当前 HeatSafe Evidence 的行动优先级辅助，不代表措施实施后的风险下降幅度，也不构成未来情景预测。")
        return "\n".join(lines).strip()

    @staticmethod
    def _hotspot_actions(result: ToolResult) -> str:
        data = result.data if isinstance(result.data, dict) else {}
        items = data.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError("hotspot action renderer requires overview items")
        facts = result.evidence
        lines = ["当前返回热点的行动优先级概览："]
        for item in items:
            grid_id = item["grid_id"]
            rank = _fact_value(facts, "hotspot_rank", item["hotspot_rank"], grid_id)
            family = _fact_value(facts, "action_family", item["top_action_family"], grid_id)
            signal = _fact_value(facts, "action_signal_points", item["top_action_signal_points"], grid_id)
            population = _fact(facts, "population_total", grid_id)
            lines.append(
                f"• 热点排名 {_integer(rank.value)} · 格网 {grid_id} [{rank.evidence_id}]："
                f"优先方向为 {_action_family_label(item['top_action_family'])} [{family.evidence_id}]；"
                f"排序信号 {_decimal(signal.value, 1)} 分 [{signal.evidence_id}]；"
                f"人口约 {_grouped(population.value)} 人 [{population.evidence_id}]。"
            )
        status = _fact(facts, "recommendation_status")
        lines.append(f"建议状态：DECISION_SUPPORT_HEURISTIC [{status.evidence_id}]。")
        lines.append("该概览只表示当前热点的行动关注方向，不是预算配置、设施选址或措施效果预测。")
        return "\n".join(lines)

    @staticmethod
    def _query(result: ToolResult) -> str:
        rows = result.data if isinstance(result.data, list) else []
        facts = result.evidence
        total = _fact(facts, "query_total_match_count")
        returned = _fact(facts, "query_result_count")
        analysis = _optional_fact(facts, "query_filter", label_prefix="analysis_status")
        thresholds = [fact for fact in facts if fact.metric == "query_threshold" and fact.evidence_id]
        threshold_by_field = {fact.label.removesuffix(" threshold"): fact for fact in thresholds}
        exposure_threshold = threshold_by_field.get("exposure_score")
        green_threshold = threshold_by_field.get("green_fraction_land")
        population_threshold = threshold_by_field.get("population_total")
        lst_threshold = threshold_by_field.get("lst_median_c")
        risk_threshold = threshold_by_field.get("risk_score")
        sort_fact = _optional_metric_fact(facts, "query_sort")
        sort_field = str(sort_fact.value) if sort_fact is not None else None
        scale = _fact(facts, "risk_scale_max")

        parts = [
            f"共找到 {_integer(total.value)} 个满足全部条件的格网 [{total.evidence_id}]，本次返回 {_integer(returned.value)} 个 [{returned.evidence_id}]。"
        ]
        conditions = []
        if analysis is not None:
            conditions.append(f"仅包含可分析陆地 [{analysis.evidence_id}]")
        if exposure_threshold is not None:
            conditions.append(f"暴露评分不低于 {_decimal(exposure_threshold.value, 2)} [{exposure_threshold.evidence_id}]")
        if green_threshold is not None:
            conditions.append(f"绿地比例不低于 {_percent(green_threshold.value)}（分析区域 P75）[{green_threshold.evidence_id}]")
        if population_threshold is not None:
            conditions.append(f"人口大于 {_integer(population_threshold.value)} 人 [{population_threshold.evidence_id}]")
        if lst_threshold is not None:
            conditions.append(f"LST 中位数不低于 {_decimal(lst_threshold.value, 1)}°C（分析区域 P75）[{lst_threshold.evidence_id}]")
        if risk_threshold is not None:
            conditions.append(f"风险不低于 {_decimal(risk_threshold.value, 1)} / {_integer(scale.value)}（分析区域 P75）[{risk_threshold.evidence_id}] [{scale.evidence_id}]")
        if sort_fact is not None:
            direction = "从多到少" if sort_fact.method == "QUERY_SORT_DESC" else "从少到多"
            conditions.append(f"按 {_query_metric_label(sort_field)} {direction}排序 [{sort_fact.evidence_id}]")
        if conditions:
            parts.append("筛选条件：" + "；".join(conditions) + "。")

        for row in rows[:3]:
            grid_id = row["grid_id"]
            grid = _fact(facts, "grid_result", grid_id)
            values = []
            rendered_metrics: set[str] = set()
            if exposure_threshold is not None:
                exposure = _fact(facts, "exposure_score", grid_id)
                values.append(f"暴露评分 {_decimal(exposure.value, 2)} [{exposure.evidence_id}]")
                rendered_metrics.add("exposure_score")
            if green_threshold is not None:
                green = _fact(facts, "green_fraction_land", grid_id)
                values.append(f"绿地比例 {_percent(green.value)} [{green.evidence_id}]")
                rendered_metrics.add("green_fraction_land")
            if population_threshold is not None:
                population = _fact(facts, "population_total", grid_id)
                values.append(f"人口约 {_grouped(population.value)} 人 [{population.evidence_id}]")
                rendered_metrics.add("population_total")
            if lst_threshold is not None:
                lst = _fact(facts, "lst_median_c", grid_id)
                values.append(f"LST 中位数 {_decimal(lst.value, 1)}°C [{lst.evidence_id}]")
                rendered_metrics.add("lst_median_c")
            if sort_field and sort_field not in rendered_metrics:
                sort_value = _optional_numeric_fact(facts, sort_field, grid_id)
                if sort_value is not None:
                    values.append(_query_metric_value(sort_field, sort_value))
                    rendered_metrics.add(sort_field)
            risk = _optional_numeric_fact(facts, "risk_score", grid_id)
            if risk is not None and "risk_score" not in rendered_metrics:
                values.append(f"风险 {_decimal(risk.value, 1)} / {_integer(scale.value)} [{risk.evidence_id}] [{scale.evidence_id}]")
            parts.append(f"• 格网 {grid_id} [{grid.evidence_id}]：" + "；".join(values) + "。")
        return "\n\n".join(parts)

    @staticmethod
    def _hotspots(result: ToolResult) -> str:
        rows = result.data if isinstance(result.data, list) else []
        scale = _fact(result.evidence, "risk_scale_max")
        parts = ["当前分析区域的高风险格网如下："]
        for row in rows:
            risk = _fact(result.evidence, "risk_score", row["grid_id"])
            dominant = _optional_metric_fact(result.evidence, "dominant_weighted_contribution", row["grid_id"])
            driver_text = f"；最大加权贡献项为 {_contribution_label(dominant.value)} [{dominant.evidence_id}]" if dominant is not None else ""
            parts.append(
                f"• 格网 {row['grid_id']}：风险 {_decimal(risk.value, 1)} / {_integer(scale.value)} "
                f"[{risk.evidence_id}] [{scale.evidence_id}]{driver_text}。"
            )
        if any(item.metric == "dominant_weighted_contribution" for item in result.evidence):
            parts.append("这里的“最大加权贡献项”表示四项加权贡献中的最大项，不表示因果关系。")
        return "\n".join(parts)

    @staticmethod
    def _summary(result: ToolResult, user_text: str, selected_grid_id: str | None) -> str:
        facts = result.evidence
        total = _fact(facts, "total_grid_count")
        land = _fact(facts, "analyzable_land_grid_count")
        water = _fact(facts, "water_excluded_grid_count")
        population = _fact(facts, "total_population_est")
        scope = _optional_metric_fact(facts, "risk_scope")
        data_mode = _optional_metric_fact(facts, "data_mode")
        model_status = _optional_metric_fact(facts, "model_status")
        scope_text = f"风险范围为当前分析区域内相对风险 [{scope.evidence_id}]。" if scope is not None else ""
        status_text = ""
        if data_mode is not None:
            status_text += f"数据模式：{data_mode.value} [{data_mode.evidence_id}]。"
        if model_status is not None:
            status_text += f"模型状态：{model_status.value} [{model_status.evidence_id}]。"
        summary = (
            f"HeatSafe 分析区域包含 {_integer(total.value)} 个格网 [{total.evidence_id}]，其中 {_integer(land.value)} 个为可分析陆地 "
            f"[{land.evidence_id}]，{_integer(water.value)} 个为水体排除格网 [{water.evidence_id}]。"
            f"分析区域估算总人口约 {_grouped(population.value)} 人 [{population.evidence_id}]。"
            + scope_text + status_text
        )
        if grid_context_required(user_text) and selected_grid_id is None:
            return (
                "当前没有选中格网。请先在地图上选择一个格网，我可以继续解释其风险、人口、LST、绿地和风险构成。\n\n"
                + summary
            )
        return summary

    @staticmethod
    def _methodology(result: ToolResult) -> str:
        methodology = _fact(result.evidence, "methodology")
        topic = methodology.label or "overview"
        return f"HeatSafe 方法说明（{topic}）：{methodology.value} [{methodology.evidence_id}]"


def _fact(
    evidence: list[EvidenceFact],
    metric: str,
    grid_id: str | None = None,
) -> EvidenceFact:
    item = next((fact for fact in evidence if fact.metric == metric and (grid_id is None or fact.grid_id == grid_id)), None)
    if item is None or not item.evidence_id:
        raise ValueError(f"renderer evidence is missing: {metric} ({grid_id or 'global'})")
    return item


def _optional_fact(evidence: list[EvidenceFact], metric: str, *, label_prefix: str) -> EvidenceFact | None:
    return next((fact for fact in evidence if fact.metric == metric and fact.label.startswith(label_prefix) and fact.evidence_id), None)


def _optional_metric_fact(evidence: list[EvidenceFact], metric: str, grid_id: str | None = None) -> EvidenceFact | None:
    return next(
        (fact for fact in evidence if fact.metric == metric and (grid_id is None or fact.grid_id == grid_id) and fact.evidence_id),
        None,
    )


def _water_explanation(result: ToolResult) -> str | None:
    data = result.data if isinstance(result.data, dict) else {}
    grid_id = data.get("grid_id")
    if not isinstance(grid_id, str):
        return None
    status = _optional_metric_fact(result.evidence, "analysis_status", grid_id)
    water = _optional_numeric_fact(result.evidence, "water_fraction_grid", grid_id)
    policy = _optional_metric_fact(result.evidence, "water_exclusion_policy")
    if status is None or status.value != "NON_URBAN_WATER" or water is None or policy is None:
        return None
    return (
        f"格网 {grid_id} 的分析状态为 NON_URBAN_WATER [{status.evidence_id}]，水体比例为 {_percent(water.value)} "
        f"[{water.evidence_id}]。\n\n根据 HeatSafe 水体排除政策 [{policy.evidence_id}]，这类格网不参与风险评分，"
        "因此风险值显示为不可用，而不是风险为零。"
    )


def _optional_numeric_fact(
    evidence: list[EvidenceFact],
    metric: str,
    grid_id: str | None = None,
) -> EvidenceFact | None:
    return next(
        (
            fact
            for fact in evidence
            if fact.metric == metric
            and (grid_id is None or fact.grid_id == grid_id)
            and fact.evidence_id
            and isinstance(fact.value, (int, float))
            and not isinstance(fact.value, bool)
        ),
        None,
    )


def _decimal(value: Any, places: int) -> str:
    return f"{float(value):.{places}f}"


def _integer(value: Any) -> str:
    return str(round(float(value)))


def _grouped(value: Any) -> str:
    return f"{round(float(value)):,}"


def _signed(value: Any, places: int) -> str:
    numeric = float(value)
    if round(numeric, places) == 0:
        return f"{0:.{places}f}"
    return f"{numeric:+.{places}f}"


def _signed_integer(value: Any) -> str:
    numeric = round(float(value))
    return "0" if numeric == 0 else f"{numeric:+d}"


def _percent(value: Any) -> str:
    return f"{float(value) * 100:.1f}%"


def _signed_percent(value: Any) -> str:
    numeric = float(value) * 100
    return "0.0%" if round(numeric, 1) == 0 else f"{numeric:+.1f}%"


def _is_compare_request(text: str) -> bool:
    lower = text.lower()
    return ("哪个热点" in text and "人口" in text) or any(token in text for token in ("比较", "区别", "不同", "第二名", "次高")) or any(
        token in lower for token in ("compare", "difference", "second", "top 2", "top2")
    )


def _contribution_label(value: Any) -> str:
    return {
        "hazard": "Hazard",
        "exposure": "Exposure",
        "vulnerability": "Vulnerability",
        "adaptive_capacity_deficit": "Adaptive deficit",
    }.get(str(value), str(value))


def _query_metric_label(metric: str | None) -> str:
    return {
        "population_total": "人口",
        "lst_median_c": "LST 中位数",
        "exposure_score": "暴露评分",
        "green_fraction_land": "绿地比例",
        "risk_score": "风险",
    }.get(str(metric), str(metric))


def _query_metric_value(metric: str, fact: EvidenceFact) -> str:
    if metric == "population_total":
        return f"人口约 {_grouped(fact.value)} 人 [{fact.evidence_id}]"
    if metric == "lst_median_c":
        return f"LST 中位数 {_decimal(fact.value, 1)}°C [{fact.evidence_id}]"
    if metric == "green_fraction_land":
        return f"绿地比例 {_percent(fact.value)} [{fact.evidence_id}]"
    if metric == "exposure_score":
        return f"暴露评分 {_decimal(fact.value, 2)} [{fact.evidence_id}]"
    if metric == "risk_score":
        return f"风险 {_decimal(fact.value, 1)} [{fact.evidence_id}]"
    return f"{metric} {_decimal(fact.value, 2)} [{fact.evidence_id}]"


def _fact_value(
    evidence: list[EvidenceFact],
    metric: str,
    value: Any,
    grid_id: str | None = None,
) -> EvidenceFact:
    item = next((
        fact for fact in evidence
        if fact.metric == metric
        and (grid_id is None or fact.grid_id == grid_id)
        and fact.value == value
        and fact.evidence_id
    ), None)
    if item is None:
        raise ValueError(f"missing grounded action evidence: {metric}")
    return item


def _action_signal_label(metric: str) -> str:
    return {
        "hazard_contribution_points": "Hazard ",
        "exposure_contribution_points": "Exposure ",
        "vulnerability_contribution_points": "Vulnerability ",
        "adaptive_deficit_contribution_points": "Adaptive deficit ",
    }.get(metric, f"{metric} ")


def _action_family_label(family: str) -> str:
    return {
        "HEAT_EXPOSURE_MITIGATION": "热暴露缓解",
        "POPULATION_EXPOSURE_MANAGEMENT": "人口暴露管理",
        "VULNERABLE_POPULATION_PROTECTION": "脆弱人群保护",
        "ADAPTIVE_CAPACITY_ENHANCEMENT": "适应能力提升",
    }.get(family, family)


def _action_context_metrics(family: str) -> tuple[str, ...]:
    return {
        "HEAT_EXPOSURE_MITIGATION": ("lst_median_c",),
        "POPULATION_EXPOSURE_MANAGEMENT": ("population_total",),
        "VULNERABLE_POPULATION_PROTECTION": ("elderly_share", "child_share"),
        "ADAPTIVE_CAPACITY_ENHANCEMENT": ("green_fraction_land",),
    }.get(family, ())


def _action_context_value(metric: str, item: EvidenceFact) -> str:
    if metric == "lst_median_c":
        return f"LST 中位数 {_decimal(item.value, 1)}°C [{item.evidence_id}]。"
    if metric == "population_total":
        return f"人口约 {_grouped(item.value)} 人 [{item.evidence_id}]。"
    if metric == "elderly_share":
        return f"老年人口占比 {_percent(item.value)} [{item.evidence_id}]。"
    if metric == "child_share":
        return f"儿童占比 {_percent(item.value)} [{item.evidence_id}]。"
    if metric == "green_fraction_land":
        return f"绿地比例 {_percent(item.value)} [{item.evidence_id}]。"
    return f"{metric} {_decimal(item.value, 2)} [{item.evidence_id}]。"


def _render_english(result: ToolResult, user_text: str, selected_grid_id: str | None) -> str:
    renderers = {
        "explain_risk": _explain_english,
        "inspect_grid": _inspect_english,
        "compare_grids": lambda item: _compare_english(item, user_text),
        "query_grids": _query_english,
        "list_hotspots": lambda item: _hotspots_english(item, user_text),
        "get_demo_summary": lambda item: _summary_english(item, user_text, selected_grid_id),
        "get_methodology": _methodology_english,
        "recommend_actions": _actions_english,
    }
    renderer = renderers.get(result.tool_name)
    if renderer is None:
        raise ValueError(f"structured renderer does not support: {result.tool_name}")
    return renderer(result)


def _water_explanation_english(result: ToolResult) -> str | None:
    data = result.data if isinstance(result.data, dict) else {}
    grid_id = data.get("grid_id")
    if not isinstance(grid_id, str):
        return None
    status = _optional_metric_fact(result.evidence, "analysis_status", grid_id)
    water = _optional_numeric_fact(result.evidence, "water_fraction_grid", grid_id)
    policy = _optional_metric_fact(result.evidence, "water_exclusion_policy")
    if status is None or status.value != "NON_URBAN_WATER" or water is None or policy is None:
        return None
    return (
        f"Grid {grid_id} is classified as excluded water [{status.evidence_id}], with {_percent(water.value)} water cover "
        f"[{water.evidence_id}].\n\nUnder the HeatSafe water-exclusion policy [{policy.evidence_id}], this grid is not risk-scored. "
        "Its risk is unavailable, not zero."
    )


def _explain_english(result: ToolResult) -> str:
    data = result.data if isinstance(result.data, dict) else {}
    grid_id = data.get("grid_id")
    if not isinstance(grid_id, str) or not grid_id:
        raise ValueError("explain renderer requires a grid ID")
    water = _water_explanation_english(result)
    if water is not None:
        return water
    facts = result.evidence
    risk = _optional_numeric_fact(facts, "risk_score", grid_id)
    scale = _optional_numeric_fact(facts, "risk_scale_max")
    if risk is None or scale is None:
        return f"Grid {grid_id} has no available relative risk score within the analysis area. HeatSafe will not invent substitute values."
    percentile = _optional_numeric_fact(facts, "risk_percentile_percent", grid_id)
    dominant = _fact(facts, "dominant_weighted_contribution", grid_id)
    labels = {
        "hazard": "Hazard",
        "exposure": "Exposure",
        "vulnerability": "Vulnerability",
        "adaptive_capacity_deficit": "Adaptive capacity deficit",
    }
    parts = [f"Grid {grid_id} has relative risk {_decimal(risk.value, 1)} / {_integer(scale.value)} within the analysis area [{risk.evidence_id}] [{scale.evidence_id}]."]
    if percentile is not None:
        parts.append(f"Its risk percentile is {_decimal(percentile.value, 1)}% [{percentile.evidence_id}].")
    contributions = []
    for metric, key in (
        ("hazard_contribution_points", "hazard"),
        ("exposure_contribution_points", "exposure"),
        ("vulnerability_contribution_points", "vulnerability"),
        ("adaptive_deficit_contribution_points", "adaptive_capacity_deficit"),
    ):
        item = _optional_numeric_fact(facts, metric, grid_id)
        if item is not None:
            contributions.append(f"{labels[key]} {_decimal(item.value, 1)} points [{item.evidence_id}]")
    if contributions:
        parts.append("Weighted contributions: " + "; ".join(contributions) + ".")
    observations = []
    for metric, label, formatter in (
        ("lst_median_c", "Median LST", lambda value: f"{_decimal(value, 1)}°C"),
        ("population_total", "Population", _grouped),
        ("green_fraction_land", "Green fraction", _percent),
        ("elderly_share", "Older-adult share", _percent),
        ("child_share", "Child share", _percent),
    ):
        item = _optional_numeric_fact(facts, metric, grid_id)
        if item is not None:
            observations.append(f"{label} {formatter(item.value)} [{item.evidence_id}]")
    if observations:
        parts.append("Supporting observations: " + "; ".join(observations) + ".")
    parts.append(f"The largest weighted contribution is {labels.get(str(dominant.value), str(dominant.value))} [{dominant.evidence_id}]. This describes model composition, not causation.")
    parts.append("The score supports relative prioritization within this analysis area; it is not absolute citywide risk or an individual health or mortality probability.")
    return "\n\n".join(parts)


def _inspect_english(result: ToolResult) -> str:
    data = result.data if isinstance(result.data, dict) else {}
    grid_id = data.get("grid_id")
    if not isinstance(grid_id, str) or not grid_id:
        raise ValueError("inspect renderer requires a grid ID")
    water = _water_explanation_english(result)
    if water is not None:
        return water
    facts = result.evidence
    lines = [f"Grid {grid_id}"]
    scale = _optional_numeric_fact(facts, "risk_scale_max")
    for metric, label, formatter in (
        ("risk_score", "Relative risk", lambda value: f"{_decimal(value, 1)} / {_integer(scale.value)}" if scale else _decimal(value, 1)),
        ("risk_percentile_percent", "Risk percentile", lambda value: f"{_decimal(value, 1)}%"),
        ("population_total", "Population", _grouped),
        ("lst_median_c", "Median LST", lambda value: f"{_decimal(value, 1)}°C"),
        ("green_fraction_land", "Green fraction", _percent),
        ("water_fraction_grid", "Water fraction", _percent),
        ("elderly_share", "Older-adult share", _percent),
        ("child_share", "Child share", _percent),
    ):
        item = _optional_numeric_fact(facts, metric, grid_id)
        if item is not None:
            citation = f" [{item.evidence_id}]" + (f" [{scale.evidence_id}]" if metric == "risk_score" and scale else "")
            lines.append(f"{label}: {formatter(item.value)}{citation}.")
    lines.append("These metrics support relative comparison within the analysis area, not absolute health or mortality risk.")
    return "\n\n".join(lines)


def _compare_english(result: ToolResult, user_text: str) -> str:
    data = result.data if isinstance(result.data, dict) else {}
    grids = data.get("grids", [])
    if compare_mode(user_text) == CompareMode.SET:
        return _set_population_comparison_english(result)
    if len(grids) != 2:
        raise ValueError("compare renderer requires exactly two grids")
    current, peer = grids
    facts = result.evidence
    current_risk = _fact(facts, "risk_score", current["grid_id"])
    peer_risk = _fact(facts, "risk_score", peer["grid_id"])
    scale = _fact(facts, "risk_scale_max")
    lines = [
        f"Selected grid {current['grid_id']} has relative risk {_decimal(current_risk.value, 1)} / {_integer(scale.value)} [{current_risk.evidence_id}] [{scale.evidence_id}]; "
        f"the second-ranked grid {peer['grid_id']} has {_decimal(peer_risk.value, 1)} / {_integer(scale.value)} [{peer_risk.evidence_id}] [{scale.evidence_id}]."
    ]
    differences = []
    for metric, label, formatter in (
        ("risk_delta", "Risk difference", lambda value: f"{_signed(value, 1)} points"),
        ("hazard_delta", "Hazard difference", lambda value: _signed(value, 2)),
        ("exposure_score_delta", "Exposure difference", lambda value: _signed(value, 2)),
        ("population_delta", "Population difference", _signed_integer),
        ("lst_delta", "LST difference", lambda value: f"{_signed(value, 1)}°C"),
        ("green_delta", "Green-fraction difference", _signed_percent),
    ):
        item = _fact(facts, metric, peer["grid_id"])
        differences.append(f"{label} {formatter(item.value)} [{item.evidence_id}]")
    lines.append("Second-ranked grid minus selected grid: " + "; ".join(differences) + ".")
    lines.append("This is a relative comparison within the current analysis area, not absolute health or mortality risk.")
    return "\n\n".join(lines)


def _set_population_comparison_english(result: ToolResult) -> str:
    data = result.data if isinstance(result.data, dict) else {}
    grids = data.get("grids", []) if result.tool_name == "compare_grids" else result.data
    if not isinstance(grids, list) or len(grids) < 2:
        raise ValueError("set comparison requires at least two grids")
    populations = [(grid, _fact(result.evidence, "population_total", grid["grid_id"])) for grid in grids]
    maximum = max(float(item.value) for _, item in populations)
    maxima = [(grid, item) for grid, item in populations if float(item.value) == maximum]
    lines = ["Population comparison within the returned hotspot set:"]
    lines.extend(f"• Grid {grid['grid_id']}: approximately {_grouped(item.value)} people [{item.evidence_id}]." for grid, item in populations)
    if len(maxima) == 1:
        grid, item = maxima[0]
        lines.append(f"Grid {grid['grid_id']} has the largest population in this returned hotspot set: approximately {_grouped(item.value)} people [{item.evidence_id}].")
    else:
        refs = ", ".join(f"grid {grid['grid_id']} [{item.evidence_id}]" for grid, item in maxima)
        lines.append(f"The largest population is tied by {refs}, each with approximately {_grouped(maxima[0][1].value)} people [{maxima[0][1].evidence_id}].")
    lines.append("This claim applies only to the returned hotspot set, not all grids in Hangzhou or another area.")
    return "\n".join(lines)


def _actions_english(result: ToolResult) -> str:
    data = result.data if isinstance(result.data, dict) else {}
    if data.get("scope") == "hotspots":
        items = data.get("items", [])
        if not items:
            raise ValueError("hotspot action renderer requires overview items")
        lines = ["Action-priority overview for the returned hotspots:"]
        for item in items:
            grid_id = item["grid_id"]
            rank = _fact_value(result.evidence, "hotspot_rank", item["hotspot_rank"], grid_id)
            family = _fact_value(result.evidence, "action_family", item["top_action_family"], grid_id)
            signal = _fact_value(result.evidence, "action_signal_points", item["top_action_signal_points"], grid_id)
            population = _fact(result.evidence, "population_total", grid_id)
            lines.append(f"• Hotspot {_integer(rank.value)} · Grid {grid_id} [{rank.evidence_id}]: {_action_family_label_english(item['top_action_family'])} [{family.evidence_id}], priority signal {_decimal(signal.value, 1)} points [{signal.evidence_id}], population approximately {_grouped(population.value)} [{population.evidence_id}].")
        status = _fact(result.evidence, "recommendation_status")
        lines.append(f"Recommendation status: DECISION_SUPPORT_HEURISTIC [{status.evidence_id}].")
        lines.append("This overview does not provide budget allocation, facility siting, or intervention-effect predictions.")
        return "\n".join(lines)
    grid_id = data.get("grid_id")
    cards = data.get("action_cards", [])
    if not isinstance(grid_id, str) or not cards:
        raise ValueError("grid action renderer requires an action plan")
    lines = [f"Action priorities for grid {grid_id}:"]
    for card in cards:
        rank = _fact_value(result.evidence, "action_priority_rank", card["priority_rank"], grid_id)
        family = _fact_value(result.evidence, "action_family", card["action_family"], grid_id)
        signal = _fact_value(result.evidence, "action_signal_points", card["signal_points"], grid_id)
        lines.extend([
            f"Priority {_integer(rank.value)} · {card['title_en']} [{rank.evidence_id}] [{family.evidence_id}]",
            "Recommended actions:",
            *[f"• {action}" for action in card["recommended_actions_en"]],
            f"Why: {_action_signal_label(card['signal_metric']).strip()} weighted contribution {_decimal(signal.value, 1)} points [{signal.evidence_id}].",
        ])
        for metric in _action_context_metrics(card["action_family"]):
            item = _optional_numeric_fact(result.evidence, metric, grid_id)
            if item is not None:
                lines.append(_action_context_value_english(metric, item))
        guidance = [item for item in result.evidence if item.metric == "action_guidance_ref" and item.grid_id == grid_id and item.value in card["guidance_ids"]]
        if guidance:
            lines.append("Action family informed by public WHO / UN-Habitat urban heat guidance " + " ".join(f"[{item.evidence_id}]" for item in guidance) + ".")
        lines.append("")
    status = _fact(result.evidence, "recommendation_status", grid_id)
    lines.append(f"Recommendation status: DECISION_SUPPORT_HEURISTIC [{status.evidence_id}].")
    lines.append("These recommendations support action prioritization from current HeatSafe Evidence. They do not estimate risk reduction after implementation. This is not a future scenario forecast.")
    return "\n".join(lines).strip()


def _query_english(result: ToolResult) -> str:
    rows = result.data if isinstance(result.data, list) else []
    facts = result.evidence
    total = _fact(facts, "query_total_match_count")
    returned = _fact(facts, "query_result_count")
    scale = _fact(facts, "risk_scale_max")
    thresholds = [item for item in facts if item.metric == "query_threshold" and item.evidence_id]
    sort_fact = _optional_metric_fact(facts, "query_sort")
    parts = [f"Found {_integer(total.value)} grids matching all conditions [{total.evidence_id}]; {_integer(returned.value)} are returned [{returned.evidence_id}]."]
    if thresholds:
        parts.append("Grounded thresholds: " + "; ".join(f"{item.label} {_decimal(item.value, 2)} [{item.evidence_id}]" for item in thresholds) + ".")
    if sort_fact is not None:
        direction = "descending" if sort_fact.method == "QUERY_SORT_DESC" else "ascending"
        parts.append(f"Results are sorted by {_query_metric_label_english(str(sort_fact.value))}, {direction} [{sort_fact.evidence_id}].")
    for row in rows[:3]:
        grid_id = row["grid_id"]
        grid = _fact(facts, "grid_result", grid_id)
        values = []
        for metric in ("population_total", "lst_median_c", "exposure_score", "green_fraction_land"):
            item = _optional_numeric_fact(facts, metric, grid_id)
            if item is not None:
                values.append(_query_metric_value_english(metric, item))
        risk = _optional_numeric_fact(facts, "risk_score", grid_id)
        if risk is not None:
            values.append(f"risk {_decimal(risk.value, 1)} / {_integer(scale.value)} [{risk.evidence_id}] [{scale.evidence_id}]")
        parts.append(f"• Grid {grid_id} [{grid.evidence_id}]: " + "; ".join(values) + ".")
    if not rows:
        parts.append("No analyzable land grids matched every requested condition.")
    return "\n\n".join(parts)


def _hotspots_english(result: ToolResult, user_text: str) -> str:
    if hotspot_population_max_requested(user_text) or (compare_mode(user_text) == CompareMode.SET and _is_compare_request(user_text)):
        return _set_population_comparison_english(result)
    rows = result.data if isinstance(result.data, list) else []
    scale = _fact(result.evidence, "risk_scale_max")
    lines = ["High-risk grids in the current analysis area:"]
    for row in rows:
        risk = _fact(result.evidence, "risk_score", row["grid_id"])
        dominant = _optional_metric_fact(result.evidence, "dominant_weighted_contribution", row["grid_id"])
        suffix = f"; largest weighted contribution: {_contribution_label(dominant.value)} [{dominant.evidence_id}]" if dominant else ""
        lines.append(f"• Grid {row['grid_id']}: risk {_decimal(risk.value, 1)} / {_integer(scale.value)} [{risk.evidence_id}] [{scale.evidence_id}]{suffix}.")
    if any(item.metric == "dominant_weighted_contribution" for item in result.evidence):
        lines.append("Largest weighted contribution describes model composition, not causation.")
    return "\n".join(lines)


def _summary_english(result: ToolResult, user_text: str, selected_grid_id: str | None) -> str:
    facts = result.evidence
    total = _fact(facts, "total_grid_count")
    land = _fact(facts, "analyzable_land_grid_count")
    water = _fact(facts, "water_excluded_grid_count")
    population = _fact(facts, "total_population_est")
    scope = _optional_metric_fact(facts, "risk_scope")
    data_mode = _optional_metric_fact(facts, "data_mode")
    model_status = _optional_metric_fact(facts, "model_status")
    summary = (
        f"The HeatSafe analysis area contains {_integer(total.value)} grids [{total.evidence_id}]: {_integer(land.value)} analyzable land grids [{land.evidence_id}] and "
        f"{_integer(water.value)} excluded water grids [{water.evidence_id}]. Estimated population in the analysis area is approximately {_grouped(population.value)} [{population.evidence_id}]."
    )
    if scope is not None:
        summary += f" Risk scope is relative within the analysis area [{scope.evidence_id}]."
    if data_mode is not None:
        summary += f" Data mode: {data_mode.value} [{data_mode.evidence_id}]."
    if model_status is not None:
        summary += f" Model status: {model_status.value} [{model_status.evidence_id}]."
    if grid_context_required(user_text) and selected_grid_id is None:
        return "No grid is currently selected. Select one on the map to inspect its risk, population, LST, green fraction, and risk composition.\n\n" + summary
    return summary


def _methodology_english(result: ToolResult) -> str:
    methodology = _fact(result.evidence, "methodology")
    topic = methodology.label or "overview"
    # Methodology facts are frozen source text. Preserve the cited value rather
    # than translating or altering its scientific meaning client-side.
    return f"HeatSafe methodology ({topic}): {methodology.value} [{methodology.evidence_id}]"


def _query_metric_label_english(metric: str) -> str:
    return {
        "population_total": "population",
        "lst_median_c": "median LST",
        "exposure_score": "exposure score",
        "green_fraction_land": "green fraction",
        "risk_score": "risk",
    }.get(metric, metric)


def _query_metric_value_english(metric: str, item: EvidenceFact) -> str:
    if metric == "population_total":
        return f"population approximately {_grouped(item.value)} [{item.evidence_id}]"
    if metric == "lst_median_c":
        return f"median LST {_decimal(item.value, 1)}°C [{item.evidence_id}]"
    if metric == "green_fraction_land":
        return f"green fraction {_percent(item.value)} [{item.evidence_id}]"
    if metric == "exposure_score":
        return f"exposure score {_decimal(item.value, 2)} [{item.evidence_id}]"
    return f"{metric} {_decimal(item.value, 2)} [{item.evidence_id}]"


def _action_family_label_english(family: str) -> str:
    return {
        "HEAT_EXPOSURE_MITIGATION": "Heat Exposure Mitigation",
        "POPULATION_EXPOSURE_MANAGEMENT": "Population Exposure Management",
        "VULNERABLE_POPULATION_PROTECTION": "Vulnerable Population Protection",
        "ADAPTIVE_CAPACITY_ENHANCEMENT": "Adaptive Capacity Enhancement",
    }.get(family, family)


def _action_context_value_english(metric: str, item: EvidenceFact) -> str:
    if metric == "lst_median_c":
        return f"Median LST {_decimal(item.value, 1)}°C [{item.evidence_id}]."
    if metric == "population_total":
        return f"Population approximately {_grouped(item.value)} [{item.evidence_id}]."
    if metric == "elderly_share":
        return f"Older-adult share {_percent(item.value)} [{item.evidence_id}]."
    if metric == "child_share":
        return f"Child share {_percent(item.value)} [{item.evidence_id}]."
    if metric == "green_fraction_land":
        return f"Green fraction {_percent(item.value)} [{item.evidence_id}]."
    return f"{metric} {_decimal(item.value, 2)} [{item.evidence_id}]."
