from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .schemas import AgentQueryRequest, FilterOperator, GridFilter, QueryGridsInput


QUERY_SEMANTIC_POLICY = "AGENT_QUERY_RELATIVE_SEMANTICS_V2"
HIGH_NORMALIZED_THRESHOLD = 0.75
LOW_NORMALIZED_THRESHOLD = 0.25


@dataclass(frozen=True)
class QueryIntent:
    filters: tuple[GridFilter, ...]
    labels: tuple[str, ...]
    sort_by: str | None = None
    sort_order: str | None = None
    semantic_intent: str = "UNCONSTRAINED"

    @property
    def constrained(self) -> bool:
        return bool(self.labels or self.sort_by)


def query_intent(text: str, service: Any) -> QueryIntent:
    lower = text.lower()
    filters: list[GridFilter] = []
    labels: list[str] = []

    high_terms = any(token in text for token in ("高", "较高", "比较高")) or any(
        token in lower for token in ("high", "higher")
    )
    high_exposure = (
        "高暴露" in text
        or "高人口暴露" in text
        or ("人口暴露" in text and high_terms)
        or "high exposure" in lower
        or "higher exposure" in lower
    )
    low_exposure = "低暴露" in text or "low exposure" in lower
    green_context = "绿地" in text or "绿化" in text
    good_green = any(token in text for token in (
        "绿地条件较好", "绿地条件不错", "绿地较好", "绿化相对较好", "绿化较好", "高绿地",
    )) or (green_context and any(token in text for token in ("较好", "不错", "相对好", "条件好"))) or any(
        token in lower for token in ("good green", "better green", "relatively green")
    )
    low_green = any(token in text for token in ("低绿地", "绿地较低", "绿地较差")) or "low green" in lower
    populated = any(token in text for token in ("有人口", "有人居住", "有居民", "人口大于 0", "人口大于0")) or any(
        token in lower for token in ("populated", "inhabited", "population > 0", "population greater than 0")
    )
    land_scope = any(token in text for token in ("陆地", "可分析区域", "可分析网格", "可分析格网", "非水域")) or any(
        token in lower for token in ("analyzable land", "analysable land", "non-water", "land grid")
    )
    populated_land = populated and land_scope
    lst_metric = "lst" in lower or "地表温度" in text or "热一些" in text or "高温区域" in text
    high_lst = lst_metric and (high_terms or any(token in text for token in ("热一些", "高温", "筛选")))
    high_risk = "高风险" in text or "high risk" in lower
    population_sort = any(token in text for token in (
        "按人口排序", "人口排序", "人口从多到少", "人口从高到低", "人口最多的排前面", "人口最多排前面",
    )) or any(
        token in lower for token in ("sort by population", "population order", "descending population", "population descending")
    )

    if not any((high_exposure, low_exposure, good_green, low_green, populated_land, high_lst, high_risk, population_sort)):
        return QueryIntent(filters=(), labels=())

    if land_scope or populated or not population_sort or any((high_exposure, low_exposure, good_green, low_green, high_lst, high_risk)):
        filters.append(GridFilter(field="analysis_status", op=FilterOperator.EQ, value="ANALYZABLE_LAND"))
        labels.append("ANALYZABLE_LAND")
    if high_exposure:
        filters.append(GridFilter(field="exposure_score", op=FilterOperator.GTE, value=HIGH_NORMALIZED_THRESHOLD))
        labels.append("EXPOSURE_HIGH")
    if low_exposure:
        filters.append(GridFilter(field="exposure_score", op=FilterOperator.LTE, value=LOW_NORMALIZED_THRESHOLD))
        labels.append("EXPOSURE_LOW")
    if good_green:
        filters.append(GridFilter(field="green_fraction_land", op=FilterOperator.GTE, value=service.relative_threshold("green_fraction_land", 0.75)))
        labels.append("GREEN_RELATIVELY_GOOD")
    if low_green:
        filters.append(GridFilter(field="green_fraction_land", op=FilterOperator.LTE, value=service.relative_threshold("green_fraction_land", 0.25)))
        labels.append("GREEN_RELATIVELY_LOW")
    if populated:
        filters.append(GridFilter(field="population_total", op=FilterOperator.GT, value=0))
        labels.append("POPULATION_POSITIVE")
    if high_lst:
        filters.append(GridFilter(field="lst_median_c", op=FilterOperator.GTE, value=service.relative_threshold("lst_median_c", 0.75)))
        labels.append("LST_RELATIVELY_HIGH")
    if high_risk:
        filters.append(GridFilter(field="risk_score", op=FilterOperator.GTE, value=service.relative_threshold("risk_score", 0.75)))
        labels.append("RISK_RELATIVELY_HIGH")
    semantic_intent = (
        "QUERY_HIGH_EXPOSURE_GOOD_GREEN" if high_exposure and good_green
        else "QUERY_POPULATED_LAND" if populated_land
        else "QUERY_HIGH_LST" if high_lst
        else "QUERY_POPULATION_DESC" if population_sort
        else "QUERY_CONSTRAINED"
    )
    return QueryIntent(
        filters=tuple(filters),
        labels=tuple(labels),
        sort_by="population_total" if population_sort else None,
        sort_order="desc" if population_sort else None,
        semantic_intent=semantic_intent,
    )


def query_completeness_errors(request: QueryGridsInput, intent: QueryIntent) -> list[str]:
    errors: list[str] = []
    for expected, label in zip(intent.filters, intent.labels, strict=True):
        if not any(_same_filter(actual, expected) for actual in request.filters):
            errors.append(f"missing required query constraint: {label} ({expected.field} {expected.op.value} {expected.value})")
    if intent.sort_by is not None and request.sort_by != intent.sort_by:
        errors.append(f"missing required query sort: {intent.sort_by} {intent.sort_order}")
    if intent.sort_order is not None and request.sort_order != intent.sort_order:
        errors.append(f"missing required query sort order: {intent.sort_by} {intent.sort_order}")
    return errors


def query_policy_instruction(intent: QueryIntent) -> str | None:
    if not intent.constrained:
        return None
    requirements: list[str] = []
    if intent.filters:
        filters = ", ".join(f"{item.field} {item.op.value} {item.value}" for item in intent.filters)
        requirements.append(f"its filters must include all of: {filters}")
    if intent.sort_by is not None:
        requirements.append(f"sort_by must be {intent.sort_by} and sort_order must be {intent.sort_order}")
    return (
        f"Deterministic query policy {QUERY_SEMANTIC_POLICY} applies to this request. "
        "If you call query_grids, " + "; and ".join(requirements) + ". "
        "Do not omit an explicit user constraint and do not substitute another threshold or sort."
    )


def normalize_compare_arguments(
    arguments: dict[str, Any],
    request: AgentQueryRequest,
    latest: str,
    service: Any,
) -> tuple[dict[str, Any], bool]:
    normalized = dict(arguments)
    raw_ids = normalized.get("grid_ids", [])
    if raw_ids is None:
        raw_ids = []
    if not isinstance(raw_ids, list):
        raise ValueError("compare_grids grid_ids must be a list")

    selected = request.context.selected_grid_id
    resolved: list[str] = []
    changed = False
    for raw in raw_ids:
        value = str(raw).strip()
        if service.repository.has_grid(value):
            resolved.append(value)
            continue
        reference = value.lower()
        if reference in {"selected", "current", "this", "selected_grid", "当前", "这里", "这个", "它"}:
            if not selected:
                raise ValueError("selected grid reference requires selected_grid_id")
            resolved.append(selected)
            changed = True
            continue
        rank = _rank_reference(reference)
        if rank is not None:
            resolved.append(service.resolve_hotspot_rank(rank))
            changed = True
            continue
        raise ValueError(f"unresolvable compare grid reference: {value}")

    if _mentions_second_rank(latest):
        if selected:
            rank_two = service.resolve_hotspot_rank(2)
            exact_pair = [selected, rank_two]
            changed = changed or resolved != exact_pair
            resolved = exact_pair
        elif len(resolved) < 2:
            raise ValueError("second-rank comparison requires selected_grid_id or two resolved grid IDs")

    deduplicated = list(dict.fromkeys(resolved))
    changed = changed or deduplicated != raw_ids
    if len(deduplicated) < 2:
        raise ValueError("compare_grids requires two resolvable grid IDs")
    if any(not service.repository.has_grid(grid_id) for grid_id in deduplicated):
        raise ValueError("compare_grids contains an unknown grid ID")
    normalized["grid_ids"] = deduplicated
    return normalized, changed


def _same_filter(actual: GridFilter, expected: GridFilter) -> bool:
    if actual.field != expected.field or actual.op != expected.op:
        return False
    if isinstance(actual.value, (int, float)) and isinstance(expected.value, (int, float)):
        return abs(float(actual.value) - float(expected.value)) <= 1e-12
    return actual.value == expected.value


def _rank_reference(value: str) -> int | None:
    if value in {"first", "top1", "top 1", "highest", "第一", "第一名", "最高"}:
        return 1
    if value in {"second", "second-ranked hotspot", "second ranked hotspot", "rank 2", "top2", "top 2", "第二", "第二名", "次高"}:
        return 2
    return None


def _mentions_second_rank(text: str) -> bool:
    lower = text.lower()
    return any(token in text for token in ("第二名", "第二", "次高")) or any(token in lower for token in ("second", "top2", "top 2"))
