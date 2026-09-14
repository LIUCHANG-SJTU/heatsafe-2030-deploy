from __future__ import annotations

from collections.abc import Iterable
from math import floor
from typing import Any

from app.services.demo_repository import DemoRepository

from .evidence import EvidenceFact, ToolResult, fact
from .schemas import CompareGridsInput, FilterOperator, GridFilter, MethodologyTopic, QueryGridsInput


class HeatSafeQueryService:
    """Deterministic, read-only query operations over the M4C1 artifact."""

    def __init__(self, repository: DemoRepository) -> None:
        self.repository = repository
        self._relative_threshold_cache: dict[tuple[str, float], float] = {}

    def relative_threshold(self, field: str, percentile: float) -> float:
        """Return a deterministic linear percentile over frozen analyzable land grids."""
        key = (field, percentile)
        if key in self._relative_threshold_cache:
            return self._relative_threshold_cache[key]
        if percentile < 0 or percentile > 1:
            raise ValueError("percentile must be between 0 and 1")
        values = sorted(
            float(grid[field])
            for grid in self.repository.iter_grids()
            if grid.get("analysis_status") == "ANALYZABLE_LAND" and isinstance(grid.get(field), (int, float))
        )
        if not values:
            raise ValueError(f"no analyzable values for percentile field: {field}")
        position = (len(values) - 1) * percentile
        lower_index = floor(position)
        upper_index = min(lower_index + 1, len(values) - 1)
        fraction = position - lower_index
        threshold = values[lower_index] + (values[upper_index] - values[lower_index]) * fraction
        self._relative_threshold_cache[key] = threshold
        return threshold

    def resolve_hotspot_rank(self, rank: int) -> str:
        if rank < 1:
            raise ValueError("hotspot rank starts at 1")
        rows = self.repository.get_hotspots(rank)
        if len(rows) < rank:
            raise ValueError(f"hotspot rank is unavailable: {rank}")
        grid_id = str(rows[rank - 1]["grid_id"])
        if not self.repository.has_grid(grid_id):
            raise ValueError(f"hotspot rank points to unknown grid: {rank}")
        return grid_id

    def summary(self) -> ToolResult:
        summary = self.repository.get_summary()
        data = {
            "demo_id": summary["demo_id"], "event": summary["aoi"]["event"],
            "aoi": summary["aoi"], "risk_scope": summary["risk_scope"],
            "data_mode": summary["data_mode"], "model_status": summary["model_status"],
            "qa_contract_version": summary["qa_contract_version"], "summary": summary["summary"],
            "methods": summary["methods"], "weights": summary["weights"],
        }
        s = summary["summary"]
        evidence = [
            fact("total_grid_count", "Total grids", s["total_grid_count"], unit="grids"),
            fact("analyzable_land_grid_count", "Analyzable land", s["analyzable_land_grid_count"], unit="grids"),
            fact("water_excluded_grid_count", "Water excluded", s["water_excluded_grid_count"], unit="grids"),
            fact("total_population_est", "Total population", s["total_population_est"], source_component="WORLDPOP", unit="people"),
            fact("temporal_severity_score", "Temporal severity", summary["temporal_context"]["temporal_severity_score"], source_component="ERA5_LAND"),
            fact("risk_scope", "Risk scope", summary["risk_scope"], source_component="RISK_MODEL"),
        ]
        # Append categorical status facts so existing Evidence IDs remain stable.
        evidence.extend([
            fact("data_mode", "Data mode", summary["data_mode"]),
            fact("model_status", "Model status", summary["model_status"], source_component="RISK_MODEL"),
        ])
        return ToolResult(tool_name="get_demo_summary", data=data, evidence=evidence, result_count=1)

    @staticmethod
    def _grid_data(grid: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "grid_id", "analysis_status", "analysis_reasons", "ranking_eligible", "risk_score",
            "risk_percentile_within_aoi", "primary_driver", "population_total", "lst_median_c",
            "ndvi_median_land", "green_fraction_land", "water_fraction_grid", "child_share",
            "elderly_share", "hazard_score", "exposure_score", "vulnerability_score",
            "adaptive_capacity_score", "hazard_contribution_points", "exposure_contribution_points",
            "vulnerability_contribution_points", "adaptive_deficit_contribution_points",
            "landsat_quality_flag", "sentinel_quality_flag", "lst_valid_fraction", "sentinel_valid_fraction",
        )
        return {key: grid.get(key) for key in keys}

    def inspect(self, grid_id: str) -> ToolResult:
        grid = self.repository.get_grid(grid_id)
        data = self._grid_data(grid)
        gid = grid["grid_id"]
        evidence = [
            fact("risk_score", "Risk score", grid.get("risk_score"), grid_id=gid, source_component="RISK_MODEL", unit="/100"),
            fact("risk_percentile_within_aoi", "Risk percentile", grid.get("risk_percentile_within_aoi"), grid_id=gid, source_component="RISK_MODEL"),
            fact("population_total", "Population", grid.get("population_total"), grid_id=gid, source_component="WORLDPOP", unit="people"),
            fact("lst_median_c", "LST median", grid.get("lst_median_c"), grid_id=gid, source_component="LANDSAT_9", unit="°C"),
            fact("green_fraction_land", "Green fraction", grid.get("green_fraction_land"), grid_id=gid, source_component="SENTINEL_2"),
            fact("water_fraction_grid", "Water fraction", grid.get("water_fraction_grid"), grid_id=gid, source_component="SENTINEL_2"),
            fact("elderly_share", "Older adults share", grid.get("elderly_share"), grid_id=gid, source_component="WORLDPOP"),
            fact("child_share", "Children share", grid.get("child_share"), grid_id=gid, source_component="WORLDPOP"),
            fact("hazard_contribution_points", "Hazard contribution", grid.get("hazard_contribution_points"), grid_id=gid, source_component="RISK_MODEL", unit="points"),
            fact("exposure_contribution_points", "Exposure contribution", grid.get("exposure_contribution_points"), grid_id=gid, source_component="RISK_MODEL", unit="points"),
            fact("vulnerability_contribution_points", "Vulnerability contribution", grid.get("vulnerability_contribution_points"), grid_id=gid, source_component="RISK_MODEL", unit="points"),
            fact("adaptive_deficit_contribution_points", "Adaptive deficit contribution", grid.get("adaptive_deficit_contribution_points"), grid_id=gid, source_component="RISK_MODEL", unit="points"),
        ]
        evidence.append(fact("risk_scale_max", "Risk scale maximum", 100, source_component="RISK_MODEL", unit="points", method="RISK_DISPLAY_SCALE_V1"))
        percentile = grid.get("risk_percentile_within_aoi")
        if isinstance(percentile, (int, float)):
            evidence.append(fact("risk_percentile_percent", "Risk percentile display", float(percentile) * 100, grid_id=gid, source_component="RISK_MODEL", unit="%", method="DISPLAY_PERCENTILE_V1"))
        # Append new categorical facts so the established numeric Evidence IDs
        # remain stable for existing clients and qualification fixtures.
        evidence.extend([
            fact("analysis_status", "Analysis status", grid.get("analysis_status"), grid_id=gid, source_component="RISK_MODEL"),
            fact("landsat_quality_flag", "Landsat quality flag", grid.get("landsat_quality_flag"), grid_id=gid, source_component="LANDSAT_9"),
            fact("sentinel_quality_flag", "Sentinel quality flag", grid.get("sentinel_quality_flag"), grid_id=gid, source_component="SENTINEL_2"),
        ])
        return ToolResult(tool_name="inspect_grid", data=data, evidence=evidence, result_count=1)

    def hotspots(self, limit: int = 10) -> ToolResult:
        rows = []
        evidence = []
        dominant_components: list[tuple[str, str]] = []
        for rank, hotspot in enumerate(self.repository.get_hotspots(limit), start=1):
            grid = self.repository.get_grid(hotspot["grid_id"])
            dominant = _dominant_weighted_contribution(grid)
            row = {
                "rank": rank, "grid_id": hotspot["grid_id"], "risk_score": hotspot["risk_score"],
                "risk_percentile_within_aoi": grid.get("risk_percentile_within_aoi"),
                "population_total": hotspot["population_total"], "primary_driver": grid.get("primary_driver"),
                "dominant_weighted_contribution": dominant,
            }
            rows.append(row)
            dominant_components.append((row["grid_id"], dominant))
            evidence.append(fact("hotspot_rank", f"Hotspot {rank} rank", rank, grid_id=row["grid_id"], source_component="RISK_MODEL", unit="rank"))
            evidence.append(fact("risk_score", f"Hotspot {rank} risk", row["risk_score"], grid_id=row["grid_id"], source_component="RISK_MODEL", unit="/100"))
            evidence.append(fact("population_total", f"Hotspot {rank} population", row["population_total"], grid_id=row["grid_id"], source_component="WORLDPOP", unit="people"))
            percentile = row.get("risk_percentile_within_aoi")
            if isinstance(percentile, (int, float)):
                evidence.append(fact("risk_percentile_percent", f"Hotspot {rank} percentile display", float(percentile) * 100, grid_id=row["grid_id"], source_component="RISK_MODEL", unit="%", method="DISPLAY_PERCENTILE_V1"))
        evidence.append(fact("risk_scale_max", "Risk scale maximum", 100, source_component="RISK_MODEL", unit="points", method="RISK_DISPLAY_SCALE_V1"))
        # Keep established hotspot and scale Evidence IDs stable by appending
        # the new decomposition facts after them.
        for grid_id, dominant in dominant_components:
            evidence.append(fact(
                "dominant_weighted_contribution",
                "Largest weighted contribution component",
                dominant,
                grid_id=grid_id,
                source_component="RISK_MODEL",
                method="DOMINANT_WEIGHTED_CONTRIBUTION_V1",
            ))
        return ToolResult(tool_name="list_hotspots", data=rows, evidence=evidence, result_count=len(rows))

    def compare(self, request: CompareGridsInput) -> ToolResult:
        grids = [self.repository.get_grid(gid) for gid in request.grid_ids]
        rows = [self._grid_data(grid) for grid in grids]
        reference = grids[0]
        deltas = []
        for grid in grids[1:]:
            deltas.append({
                "from_grid_id": reference["grid_id"], "to_grid_id": grid["grid_id"],
                "risk_delta": _delta(grid.get("risk_score"), reference.get("risk_score")),
                "population_delta": _delta(grid.get("population_total"), reference.get("population_total")),
                "lst_delta": _delta(grid.get("lst_median_c"), reference.get("lst_median_c")),
                "green_delta": _delta(grid.get("green_fraction_land"), reference.get("green_fraction_land")),
                "hazard_delta": _delta(grid.get("hazard_score"), reference.get("hazard_score")),
                "exposure_score_delta": _delta(grid.get("exposure_score"), reference.get("exposure_score")),
            })
        evidence: list[EvidenceFact] = []
        for delta in deltas:
            evidence.extend([
                fact("risk_delta", "Risk difference", delta["risk_delta"], grid_id=delta["to_grid_id"], source_component="RISK_MODEL", method="COMPARE_DELTA_V1"),
                fact("population_delta", "Population difference", delta["population_delta"], grid_id=delta["to_grid_id"], source_component="WORLDPOP", method="COMPARE_DELTA_V1"),
                fact("lst_delta", "LST difference", delta["lst_delta"], grid_id=delta["to_grid_id"], source_component="LANDSAT_9", method="COMPARE_DELTA_V1"),
                fact("green_delta", "Green fraction difference", delta["green_delta"], grid_id=delta["to_grid_id"], source_component="SENTINEL_2", method="COMPARE_DELTA_V1"),
                fact("hazard_delta", "Hazard score difference", delta["hazard_delta"], grid_id=delta["to_grid_id"], source_component="RISK_MODEL", method="COMPARE_DELTA_V1"),
                fact("exposure_score_delta", "Exposure score difference", delta["exposure_score_delta"], grid_id=delta["to_grid_id"], source_component="RISK_MODEL", method="COMPARE_DELTA_V1"),
            ])
        for grid in grids:
            evidence.append(fact("risk_score", "Compared risk", grid.get("risk_score"), grid_id=grid["grid_id"], source_component="RISK_MODEL", unit="/100"))
            evidence.append(fact("population_total", "Compared population", grid.get("population_total"), grid_id=grid["grid_id"], source_component="WORLDPOP", unit="people"))
        evidence.append(fact("risk_scale_max", "Risk scale maximum", 100, source_component="RISK_MODEL", unit="points", method="RISK_DISPLAY_SCALE_V1"))
        for grid in grids:
            evidence.append(fact(
                "comparison_grid",
                "Pairwise comparison member",
                grid["grid_id"],
                grid_id=grid["grid_id"],
                source_component="RISK_MODEL",
                method="PAIRWISE_COMPARISON_MEMBERSHIP_V1",
            ))
        return ToolResult(tool_name="compare_grids", data={"grids": rows, "deltas": deltas}, evidence=evidence, result_count=len(rows))

    def query(self, request: QueryGridsInput) -> ToolResult:
        grids = [grid for grid in self.repository.iter_grids() if all(_matches(grid, condition) for condition in request.filters)]
        # Sort IDs first, then use a stable metric sort so ties remain grid_id ascending.
        grids.sort(key=lambda grid: grid["grid_id"])
        if request.sort_order == "desc":
            grids.sort(key=lambda grid: (grid.get(request.sort_by) is not None, _sort_value(grid.get(request.sort_by))), reverse=True)
        else:
            grids.sort(key=lambda grid: (grid.get(request.sort_by) is None, _sort_value(grid.get(request.sort_by))))
        total_matches = len(grids)
        rows = [self._grid_data(grid) for grid in grids[: request.limit]]
        evidence = [fact("query_result_count", "Query result count", len(rows), source_component="RISK_MODEL", unit="grids")]
        evidence.append(fact("query_total_match_count", "Query total matches", total_matches, source_component="RISK_MODEL", unit="grids"))
        for row in rows:
            evidence.append(fact("grid_result", "Query result", row["grid_id"], grid_id=row["grid_id"], source_component="RISK_MODEL"))
            for metric, component in (("population_total", "WORLDPOP"), ("lst_median_c", "LANDSAT_9"), ("exposure_score", "RISK_MODEL"), ("green_fraction_land", "SENTINEL_2"), ("risk_score", "RISK_MODEL")):
                if row.get(metric) is not None:
                    evidence.append(fact(metric, f"Query {metric}", row[metric], grid_id=row["grid_id"], source_component=component))
        evidence.append(fact("risk_scale_max", "Risk scale maximum", 100, source_component="RISK_MODEL", unit="points", method="RISK_DISPLAY_SCALE_V1"))
        for condition in request.filters:
            if condition.op not in {FilterOperator.GT, FilterOperator.GTE, FilterOperator.LT, FilterOperator.LTE}:
                evidence.append(fact("query_filter", f"{condition.field} filter", condition.value, source_component="RISK_MODEL", method="AGENT_QUERY_RELATIVE_SEMANTICS_V2"))
                continue
            method = "AGENT_QUERY_RELATIVE_SEMANTICS_V2"
            if condition.field in {"green_fraction_land", "lst_median_c", "risk_score"}:
                p75 = self.relative_threshold(condition.field, 0.75)
                p25 = self.relative_threshold(condition.field, 0.25)
                if abs(float(condition.value) - p75) <= 1e-12:
                    method = "DEMO_AOI_P75"
                elif abs(float(condition.value) - p25) <= 1e-12:
                    method = "DEMO_AOI_P25"
            component = "SENTINEL_2" if condition.field == "green_fraction_land" else "LANDSAT_9" if condition.field == "lst_median_c" else "WORLDPOP" if condition.field == "population_total" else "RISK_MODEL"
            evidence.append(fact("query_threshold", f"{condition.field} threshold", condition.value, source_component=component, method=method))
        evidence.append(fact(
            "query_sort",
            "Query sort field",
            request.sort_by,
            source_component="RISK_MODEL",
            method=f"QUERY_SORT_{request.sort_order.upper()}",
        ))
        return ToolResult(tool_name="query_grids", data=rows, evidence=evidence, result_count=len(rows))

    def explain(self, grid_id: str) -> ToolResult:
        result = self.inspect(grid_id)
        grid = self.repository.get_grid(grid_id)
        contributions = [
            ("hazard", grid.get("hazard_contribution_points")),
            ("exposure", grid.get("exposure_contribution_points")),
            ("vulnerability", grid.get("vulnerability_contribution_points")),
            ("adaptive_capacity_deficit", grid.get("adaptive_deficit_contribution_points")),
        ]
        available = grid.get("risk_score") is not None
        ordered = sorted(contributions, key=lambda item: item[1] if item[1] is not None else float("-inf"), reverse=True) if available else []
        data = {**result.data, "primary_driver": grid.get("primary_driver") if available else None, "contribution_ranking": [{"component": key, "points": value} for key, value in ordered], "largest_contribution": ordered[0][0] if ordered else None, "second_largest_contribution": ordered[1][0] if len(ordered) > 1 else None, "risk_available": available}
        if ordered:
            result.evidence.append(fact(
                "dominant_weighted_contribution",
                "Largest weighted contribution",
                ordered[0][0],
                grid_id=grid["grid_id"],
                source_component="RISK_MODEL",
                method="DOMINANT_WEIGHTED_CONTRIBUTION_V1",
            ))
        result.tool_name = "explain_risk"
        result.data = data
        return result

    def methodology(self, topic: MethodologyTopic) -> ToolResult:
        summary = self.repository.get_summary()
        methods = summary["methods"]
        content = {
            "overview": "HeatSafe is a read-only relative heat-risk diagnostic for the selected 5 km x 5 km analysis area.",
            "risk_formula": "Risk = 0.40 H + 0.25 E + 0.20 V + 0.15 (1-A).",
            "risk_scope": "Scores are relative within the selected analysis area, not mortality, health-outcome, or citywide absolute probabilities.",
            "hazard": "Hazard combines 0.7 within-AOI spatial LST percentile with 0.3 shared ERA5-Land temporal severity.",
            "exposure": "Exposure is the normalized log1p population proxy for each analysis grid.",
            "vulnerability": "Vulnerability = 0.7 elderly share (65+) + 0.3 child share (0-14).",
            "adaptive_capacity": "Adaptive capacity is a vegetation-based proxy from green fraction among valid land pixels; the risk term is 1-A.",
            "worldpop": "WorldPop 2026 official R2025A 100 m products are transferred to 250 m grids by fractional-area count transfer.",
            "landsat": "Landsat 9 surface temperature observations use a 100 m thermal source aggregated to 250 m grids.",
            "sentinel2": "Sentinel-2 10 m optical observations provide NDVI, green fraction, and water classification aggregated to 250 m grids.",
            "era5": "ERA5-Land supplies shared temporal heat context for the analysis area; no artificial 250 m spatial variation is created.",
            "water_rule": "Cells with water fraction >= 0.50 are NON_URBAN_WATER and have no risk score.",
            "qa": summary["qa_contract_version"],
            "limitations": "The model is PRELIMINARY_HEURISTIC and supports diagnostic prioritization, not causal policy optimization or scenario simulation.",
        }[topic.value]
        evidence = [fact("methodology", topic.value, content, source_component="RISK_MODEL", source_ref="m4c1_qa_contract")]
        if topic == MethodologyTopic.WATER_RULE:
            evidence.append(fact(
                "water_exclusion_policy",
                "Water exclusion policy",
                "NON_URBAN_WATER grids are excluded from risk scoring",
                source_component="RISK_MODEL",
                source_ref="m4c1_qa_contract",
                method="WATER_EXCLUSION_POLICY_V1",
            ))
        return ToolResult(tool_name="get_methodology", data={"topic": topic.value, "text": content, "methods": methods, "risk_scope": summary["risk_scope"]}, evidence=evidence, result_count=1)


def _delta(value: Any, reference: Any) -> float | None:
    if value is None or reference is None:
        return None
    return float(value) - float(reference)


def _dominant_weighted_contribution(grid: dict[str, Any]) -> str:
    contributions = {
        "hazard": grid.get("hazard_contribution_points"),
        "exposure": grid.get("exposure_contribution_points"),
        "vulnerability": grid.get("vulnerability_contribution_points"),
        "adaptive_capacity_deficit": grid.get("adaptive_deficit_contribution_points"),
    }
    available = {key: float(value) for key, value in contributions.items() if isinstance(value, (int, float))}
    if not available:
        raise ValueError(f"hotspot has no weighted contribution values: {grid.get('grid_id')}")
    return max(available, key=available.get)


def _sort_value(value: Any) -> Any:
    return value if value is not None else float("-inf")


def _matches(grid: dict[str, Any], condition: GridFilter) -> bool:
    actual = grid.get(condition.field)
    expected = condition.value
    if condition.op.value == "in":
        if not isinstance(expected, list):
            return False
        return actual in expected
    if actual is None:
        return False
    if condition.op.value == "eq": return actual == expected
    if condition.op.value == "gt": return actual > expected
    if condition.op.value == "gte": return actual >= expected
    if condition.op.value == "lt": return actual < expected
    if condition.op.value == "lte": return actual <= expected
    return False
