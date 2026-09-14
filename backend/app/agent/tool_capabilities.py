from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ToolEvidenceCapability:
    """Evidence metrics a public tool emits for valid invocations."""

    always_provides: frozenset[str]
    conditionally_provides: frozenset[str] = frozenset()
    completion_requires_any: frozenset[str] = frozenset()

    @property
    def may_provide(self) -> frozenset[str]:
        return self.always_provides | self.conditionally_provides

    def covers(self, slot: str) -> bool:
        if slot.startswith("one_of:"):
            alternatives = slot.removeprefix("one_of:").split("|")
            return any(alternative in self.may_provide for alternative in alternatives)
        return slot in self.may_provide

    def as_dict(self) -> dict[str, list[str]]:
        return {
            "always_provides": sorted(self.always_provides),
            "conditionally_provides": sorted(self.conditionally_provides),
            "completion_requires_any": sorted(self.completion_requires_any),
        }

    def eligible_for_completion(self, slots: tuple[str, ...]) -> bool:
        return not self.completion_requires_any or any(slot in self.completion_requires_any for slot in slots)


class ToolEvidenceCapabilities:
    """Production-semantic capability registry for public HeatSafe tools."""

    def __init__(self) -> None:
        grid_metrics = frozenset({
            "risk_score",
            "risk_percentile_within_aoi",
            "population_total",
            "lst_median_c",
            "green_fraction_land",
            "water_fraction_grid",
            "elderly_share",
            "child_share",
            "hazard_contribution_points",
            "exposure_contribution_points",
            "vulnerability_contribution_points",
            "adaptive_deficit_contribution_points",
            "risk_scale_max",
            "analysis_status",
            "landsat_quality_flag",
            "sentinel_quality_flag",
        })
        self._capabilities: dict[str, ToolEvidenceCapability] = {
            "get_demo_summary": ToolEvidenceCapability(frozenset({
                "total_grid_count",
                "analyzable_land_grid_count",
                "water_excluded_grid_count",
                "total_population_est",
                "temporal_severity_score",
                "risk_scope",
                "data_mode",
                "model_status",
            })),
            "inspect_grid": ToolEvidenceCapability(
                always_provides=grid_metrics,
                conditionally_provides=frozenset({"risk_percentile_percent"}),
            ),
            "list_hotspots": ToolEvidenceCapability(
                always_provides=frozenset({"risk_scale_max"}),
                conditionally_provides=frozenset({
                    "hotspot_rank",
                    "risk_score",
                    "population_total",
                    "risk_percentile_percent",
                    "dominant_weighted_contribution",
                }),
            ),
            "compare_grids": ToolEvidenceCapability(
                always_provides=frozenset({"risk_scale_max"}),
                conditionally_provides=frozenset({
                    "comparison_grid",
                    "risk_delta",
                    "population_delta",
                    "lst_delta",
                    "green_delta",
                    "hazard_delta",
                    "exposure_score_delta",
                    "risk_score",
                    "population_total",
                }),
            ),
            "query_grids": ToolEvidenceCapability(
                always_provides=frozenset({
                    "query_result_count",
                    "query_total_match_count",
                    "query_sort",
                    "risk_scale_max",
                }),
                conditionally_provides=frozenset({
                    "grid_result",
                    "population_total",
                    "lst_median_c",
                    "exposure_score",
                    "green_fraction_land",
                    "risk_score",
                    "query_filter",
                    "query_threshold",
                }),
            ),
            "explain_risk": ToolEvidenceCapability(
                always_provides=grid_metrics,
                conditionally_provides=frozenset({
                    "risk_percentile_percent",
                    "dominant_weighted_contribution",
                }),
            ),
            "get_methodology": ToolEvidenceCapability(
                always_provides=frozenset({"methodology"}),
                conditionally_provides=frozenset({"water_exclusion_policy"}),
            ),
            "recommend_actions": ToolEvidenceCapability(
                always_provides=frozenset({
                    "action_catalog_version",
                    "recommendation_status",
                }),
                conditionally_provides=grid_metrics | frozenset({
                    "action_priority_rank",
                    "action_family",
                    "action_signal_metric",
                    "action_signal_points",
                    "action_guidance_ref",
                    "hotspot_rank",
                    "risk_score",
                    "population_total",
                    "dominant_weighted_contribution",
                    "hazard_contribution_points",
                    "exposure_contribution_points",
                    "vulnerability_contribution_points",
                    "adaptive_deficit_contribution_points",
                    "lst_median_c",
                    "green_fraction_land",
                    "elderly_share",
                    "child_share",
                    "analysis_status",
                    "risk_scale_max",
                    "risk_percentile_percent",
                }),
                completion_requires_any=frozenset({
                    "action_priority_rank",
                    "action_family",
                    "action_signal_points",
                    "recommendation_status",
                }),
            ),
        }

    @property
    def tool_names(self) -> tuple[str, ...]:
        return tuple(self._capabilities)

    def for_tool(self, tool_name: str) -> ToolEvidenceCapability:
        try:
            return self._capabilities[tool_name]
        except KeyError as error:
            raise ValueError(f"unknown public tool capability: {tool_name}") from error

    def tools_covering_all(self, missing_slots: Iterable[str]) -> list[str]:
        slots = tuple(missing_slots)
        if not slots:
            return []
        return [
            tool_name
            for tool_name, capability in self._capabilities.items()
            if capability.eligible_for_completion(slots)
            and all(capability.covers(slot) for slot in slots)
        ]
