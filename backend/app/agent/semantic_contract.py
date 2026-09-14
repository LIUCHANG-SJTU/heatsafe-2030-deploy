from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Iterable

from .evidence import EvidenceFact


SEMANTIC_CONTRACT_VERSION = "M5B4_SEMANTIC_INTENT_CONTRACT_V1"


class CompareMode(StrEnum):
    PAIRWISE = "PAIRWISE_COMPARE"
    SET = "SET_COMPARISON"


@dataclass(frozen=True)
class SemanticRequirement:
    intent: str
    required: tuple[str, ...] = ()
    required_any: tuple[tuple[str, ...], ...] = ()
    binding: str | None = None
    expected_grid_ids: tuple[str, ...] = ()

    @property
    def constrained(self) -> bool:
        return bool(self.required or self.required_any)


@dataclass(frozen=True)
class SemanticCompleteness:
    intent: str
    status: str
    missing_slots: tuple[str, ...] = ()


class SemanticIntentContract:
    """Defines required Evidence without prescribing which public tool supplies it."""

    def identify(
        self,
        text: str,
        *,
        selected_grid_id: str | None = None,
        ranked_grid_id: str | None = None,
        query_intent: Any | None = None,
    ) -> SemanticRequirement:
        lower = text.lower()
        action_scope = action_recommendation_scope(text)
        action_required = (
            "action_priority_rank",
            "action_family",
            "action_signal_points",
            "recommendation_status",
        )
        if action_scope == "HOTSPOTS":
            return SemanticRequirement(
                "HOTSPOT_ACTION_OVERVIEW",
                ("hotspot_rank", *action_required),
                binding="ACTION_HOTSPOT_GRID_BINDING",
            )
        if action_scope == "GRID" and selected_grid_id:
            return SemanticRequirement(
                "GRID_ACTION_RECOMMENDATION",
                action_required,
                binding="ACTION_GRID_BINDING",
                expected_grid_ids=(selected_grid_id,),
            )
        if hotspot_population_max_requested(text):
            return SemanticRequirement(
                "HOTSPOT_POPULATION_MAX",
                ("hotspot_rank", "population_total"),
                binding="HOTSPOT_POPULATION_GRID_BINDING",
            )
        if selected_ranked_compare_requested(text) and selected_grid_id and ranked_grid_id:
            return SemanticRequirement(
                "SELECTED_VS_RANKED_COMPARE",
                (
                    "comparison_grid",
                    "risk_delta",
                    "population_delta",
                    "lst_delta",
                    "green_delta",
                    "hazard_delta",
                    "exposure_score_delta",
                ),
                binding="EXACT_PAIRWISE_GRID_BINDING",
                expected_grid_ids=(selected_grid_id, ranked_grid_id),
            )
        if _is_hotspot_driver_request(text):
            return SemanticRequirement(
                "HOTSPOT_DRIVER",
                ("hotspot_rank", "dominant_weighted_contribution"),
                binding="HOTSPOT_GRID_BINDING",
            )
        if compare_mode(text) == CompareMode.SET and ("热点" in text or "hotspot" in lower):
            return SemanticRequirement("SET_COMPARISON_POPULATION", ("population_total",))
        if query_intent is not None and query_intent.constrained:
            required = ["query_result_count"]
            if query_intent.filters:
                if any(item.op.value in {"eq", "in"} for item in query_intent.filters):
                    required.append("query_filter")
                if any(item.op.value in {"gt", "gte", "lt", "lte"} for item in query_intent.filters):
                    required.append("query_threshold")
            if query_intent.sort_by:
                required.append("query_sort")
            return SemanticRequirement(query_intent.semantic_intent, tuple(required))
        if ("风险范围" in text and "demo" in lower) or "risk scope" in lower:
            return SemanticRequirement("RISK_SCOPE", ("risk_scope",))
        if "绿地" in text and any(token in text for token in ("年龄", "老年", "儿童")):
            return SemanticRequirement(
                "GRID_GREEN_AND_AGE",
                ("green_fraction_land",),
                (("elderly_share", "child_share"),),
            )
        if "水域" in text and any(token in text for token in ("没有风险", "无风险", "风险值")):
            return SemanticRequirement(
                "WATER_NO_RISK_EXPLANATION",
                ("analysis_status", "water_fraction_grid", "water_exclusion_policy"),
            )
        return SemanticRequirement("UNCONSTRAINED")

    def evaluate(self, requirement: SemanticRequirement, evidence: Iterable[EvidenceFact]) -> SemanticCompleteness:
        facts = tuple(evidence)
        metrics = {item.metric for item in facts}
        missing = [slot for slot in requirement.required if slot not in metrics]
        for alternatives in requirement.required_any:
            if not any(slot in metrics for slot in alternatives):
                missing.append("one_of:" + "|".join(alternatives))
        if requirement.binding == "HOTSPOT_GRID_BINDING" and not missing:
            ranked_grids = {
                item.grid_id for item in facts
                if item.metric == "hotspot_rank" and item.grid_id
            }
            dominant_grids = {
                item.grid_id for item in facts
                if item.metric == "dominant_weighted_contribution" and item.grid_id
            }
            if not ranked_grids or not ranked_grids.issubset(dominant_grids):
                missing.append("binding:hotspot_rank_to_dominant_weighted_contribution")
        if requirement.binding == "HOTSPOT_POPULATION_GRID_BINDING" and not missing:
            ranked_grids = {
                item.grid_id for item in facts
                if item.metric == "hotspot_rank" and item.grid_id
            }
            population_grids = {
                item.grid_id for item in facts
                if item.metric == "population_total" and item.grid_id
            }
            if not ranked_grids or not ranked_grids.issubset(population_grids):
                missing.append("binding:hotspot_rank_to_population_total")
        if requirement.binding == "EXACT_PAIRWISE_GRID_BINDING" and not missing:
            compared_grids = {
                item.grid_id for item in facts
                if item.metric == "comparison_grid" and item.grid_id
            }
            if compared_grids != set(requirement.expected_grid_ids):
                missing.append("binding:exact_pairwise_comparison_grids")
        if requirement.binding == "ACTION_GRID_BINDING" and not missing:
            expected = set(requirement.expected_grid_ids)
            for metric in ("action_priority_rank", "action_family", "action_signal_points", "recommendation_status"):
                metric_grids = {item.grid_id for item in facts if item.metric == metric and item.grid_id}
                if metric_grids != expected:
                    missing.append(f"binding:{metric}_to_selected_grid")
        if requirement.binding == "ACTION_HOTSPOT_GRID_BINDING" and not missing:
            ranked_grids = {item.grid_id for item in facts if item.metric == "hotspot_rank" and item.grid_id}
            for metric in ("action_priority_rank", "action_family", "action_signal_points"):
                metric_grids = {item.grid_id for item in facts if item.metric == metric and item.grid_id}
                if not ranked_grids or not ranked_grids.issubset(metric_grids):
                    missing.append(f"binding:hotspot_rank_to_{metric}")
        return SemanticCompleteness(
            intent=requirement.intent,
            status="PASS" if not missing else "FAIL_INCOMPLETE",
            missing_slots=tuple(missing),
        )


def grid_context_required(text: str) -> bool:
    """Return whether the request refers deictically to a selected/current grid."""
    lower = text.lower()
    return any(token in text for token in ("这里", "这个格子", "这个格网", "当前格子", "当前格网", "选中格网", "选中的格网")) or any(
        token in lower for token in ("this grid", "current grid", "selected grid")
    )


def action_recommendation_scope(text: str) -> str | None:
    """Classify action semantics without prescribing a tool."""
    lower = text.lower()
    action_terms = (
        any(token in text for token in (
            "应该做什么", "优先做什么", "建议采取什么", "采取什么措施", "优先行动",
            "怎么改善", "如何改善", "如何干预", "哪类措施优先", "哪类行动", "行动建议",
        ))
        or (("应该" in text or "建议" in text or "优先" in text) and any(token in text for token in ("行动", "措施", "做什么")))
        or any(token in lower for token in (
            "what should we do", "recommended action", "recommended measures", "intervention priorities",
            "what action should be prioritized", "which action", "how should we intervene", "how can we improve",
        ))
    )
    if not action_terms:
        return None
    hotspot_terms = any(token in text for token in ("热点", "高风险区域", "高风险网格", "高风险格网")) or any(
        token in lower for token in ("hotspot", "high-risk area", "high risk area", "high-risk grid", "high risk grid")
    )
    return "HOTSPOTS" if hotspot_terms else "GRID"


def _is_hotspot_driver_request(text: str) -> bool:
    lower = text.lower()
    hotspot_terms = any(token in text for token in ("热点", "高风险区域", "高风险网格", "高风险格网")) or any(
        token in lower for token in ("hotspot", "high-risk area", "high risk area", "high-risk grid", "high risk grid")
    )
    driver_terms = any(token in text for token in ("驱动", "主导", "贡献", "主要因素")) or any(
        token in lower for token in ("dominat", "driver", "contribution", "largest component", "largest weighted component")
    )
    largest_component_question = any(token in text for token in ("哪一项", "哪个分量", "哪种分量")) and any(
        token in text for token in ("最高", "最大")
    )
    return hotspot_terms and (driver_terms or largest_component_question)


def selected_ranked_compare_requested(text: str) -> bool:
    lower = text.lower()
    compare_terms = any(token in text for token in ("比较", "比一下", "差多少", "差在哪里", "区别", "不同")) or any(
        token in lower for token in ("compare", "difference", "differ")
    )
    selected_terms = any(token in text for token in ("当前格网", "当前网格", "选中格网", "选中的格网", "这个格子", "这个格网")) or any(
        token in lower for token in ("selected grid", "current grid", "this grid")
    )
    ranked_terms = any(token in text for token in ("排名第二", "风险第二", "第二名", "次高")) or any(
        token in lower for token in ("second-ranked", "second ranked", "rank 2", "top 2", "top2")
    )
    return compare_terms and selected_terms and ranked_terms


def hotspot_population_max_requested(text: str) -> bool:
    lower = text.lower()
    hotspot_terms = any(token in text for token in (
        "热点", "高风险区域", "最高风险区域", "高风险格网", "高风险网格",
    )) or any(token in lower for token in ("hotspot", "high-risk area", "high risk area"))
    population_terms = "人口" in text or "population" in lower or "populated" in lower
    maximum_terms = any(token in text for token in ("最多", "最大", "哪一个", "哪一格", "哪个")) or any(
        token in lower for token in ("most", "maximum", "largest", "which")
    )
    return hotspot_terms and population_terms and maximum_terms


class QueryFieldCanonicalizer:
    """Canonicalize only explicitly approved query field aliases."""

    _ALIASES = {
        "population": "population_total",
        "population_count": "population_total",
        "population_total": "population_total",
        "lst": "lst_median_c",
        "land_surface_temperature": "lst_median_c",
        "surface_temperature": "lst_median_c",
        "lst_median_c": "lst_median_c",
        "green": "green_fraction_land",
        "green_fraction": "green_fraction_land",
        "green_fraction_land": "green_fraction_land",
        "exposure": "exposure_score",
        "exposure_score": "exposure_score",
        "risk": "risk_score",
        "risk_score": "risk_score",
    }

    def canonicalize(self, arguments: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        normalized = dict(arguments)
        changes: list[str] = []
        raw_filters = normalized.get("filters")
        if isinstance(raw_filters, list):
            filters: list[Any] = []
            for index, raw_filter in enumerate(raw_filters):
                if not isinstance(raw_filter, dict):
                    filters.append(raw_filter)
                    continue
                item = dict(raw_filter)
                if isinstance(item.get("field"), str):
                    item["field"] = self._canonical_field(item["field"], f"filters[{index}].field", changes)
                filters.append(item)
            normalized["filters"] = filters
        if isinstance(normalized.get("sort_by"), str):
            normalized["sort_by"] = self._canonical_field(normalized["sort_by"], "sort_by", changes)
        return normalized, changes

    def _canonical_field(self, value: str, location: str, changes: list[str]) -> str:
        canonical = self._ALIASES.get(value.strip().lower(), value)
        if canonical != value:
            changes.append(f"{location}:{value}->{canonical}")
        return canonical


def compare_mode(text: str) -> CompareMode:
    lower = text.lower()
    if hotspot_population_max_requested(text) or any(token in text for token in ("哪个热点", "这些热点", "哪些热点")) or any(
        token in lower for token in ("which hotspot", "among the hotspots")
    ):
        return CompareMode.SET
    return CompareMode.PAIRWISE
