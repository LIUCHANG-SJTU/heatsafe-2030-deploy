from __future__ import annotations

from collections.abc import Mapping

from app.agent.evidence import EvidenceFact, ToolResult, fact
from app.agent.query_service import HeatSafeQueryService

from .catalog import ACTION_CATALOG, ACTION_CATALOG_VERSION, ACTION_FAMILY_STABLE_ORDER
from .guidance import ACTION_GUIDANCE_REGISTRY
from .models import (
    ActionCard,
    ActionEvidenceRef,
    ActionFamily,
    GridActionPlan,
    HotspotActionItem,
    HotspotActionOverview,
)


RECOMMENDATION_STATUS = "DECISION_SUPPORT_HEURISTIC"
RISK_SCOPE = "RELATIVE_WITHIN_DEMO_AOI"
ACTION_LIMITATION_ZH = "该建议用于基于当前 HeatSafe Evidence 的行动优先级辅助，不代表措施实施后的风险下降幅度，也不构成未来情景预测。"
ACTION_LIMITATION_EN = "These recommendations support action prioritization from current HeatSafe Evidence. They do not estimate risk reduction after implementation or constitute a future scenario forecast."

SIGNAL_METRICS = {
    ActionFamily.HEAT_EXPOSURE_MITIGATION: "hazard_contribution_points",
    ActionFamily.POPULATION_EXPOSURE_MANAGEMENT: "exposure_contribution_points",
    ActionFamily.VULNERABLE_POPULATION_PROTECTION: "vulnerability_contribution_points",
    ActionFamily.ADAPTIVE_CAPACITY_ENHANCEMENT: "adaptive_deficit_contribution_points",
}

CONTEXT_METRICS = {
    ActionFamily.HEAT_EXPOSURE_MITIGATION: ("lst_median_c",),
    ActionFamily.POPULATION_EXPOSURE_MANAGEMENT: ("population_total",),
    ActionFamily.VULNERABLE_POPULATION_PROTECTION: ("elderly_share", "child_share"),
    ActionFamily.ADAPTIVE_CAPACITY_ENHANCEMENT: ("green_fraction_land",),
}


class ActionRecommendationService:
    def __init__(self, query_service: HeatSafeQueryService) -> None:
        self.query_service = query_service

    @staticmethod
    def rank_signals(signals: Mapping[ActionFamily, float]) -> list[tuple[ActionFamily, float]]:
        return sorted(
            ((family, float(value)) for family, value in signals.items()),
            key=lambda item: (-item[1], ACTION_FAMILY_STABLE_ORDER[item[0]]),
        )

    def recommend_for_grid(self, grid_id: str, *, limit: int = 3) -> ToolResult:
        if limit < 1 or limit > 4:
            raise ValueError("action card limit must be between 1 and 4")
        grid = self.query_service.repository.get_grid(grid_id)
        if grid.get("analysis_status") != "ANALYZABLE_LAND" or grid.get("risk_score") is None:
            raise ValueError("ACTION_PLAN_UNAVAILABLE_NON_URBAN_WATER")

        inspected = self.query_service.inspect(grid_id)
        underlying = list(inspected.evidence)
        by_metric = {item.metric: item for item in underlying}
        signals = {
            family: float(grid[metric])
            for family, metric in SIGNAL_METRICS.items()
        }
        ranked = self.rank_signals(signals)[:limit]

        derived: list[EvidenceFact] = [
            fact(
                "action_catalog_version",
                "Action catalog version",
                ACTION_CATALOG_VERSION,
                grid_id=grid_id,
                source_component="ACTION_ENGINE",
                method="GROUNDED_ACTION_CATALOG_V1",
            ),
            fact(
                "recommendation_status",
                "Recommendation status",
                RECOMMENDATION_STATUS,
                grid_id=grid_id,
                source_component="ACTION_ENGINE",
                method="DETERMINISTIC_ACTION_PRIORITY_V1",
            ),
        ]
        cards: list[ActionCard] = []
        guidance_ids: list[str] = []
        for priority_rank, (family, signal_points) in enumerate(ranked, start=1):
            signal_metric = SIGNAL_METRICS[family]
            entry = ACTION_CATALOG[family]
            guidance_ids.extend(entry.guidance_ids)
            supporting = [by_metric[signal_metric]]
            supporting.extend(by_metric[metric] for metric in CONTEXT_METRICS[family] if metric in by_metric)
            cards.append(ActionCard(
                priority_rank=priority_rank,
                action_family=family,
                title_zh=entry.title_zh,
                title_en=entry.title_en,
                recommended_actions_zh=list(entry.actions_zh),
                recommended_actions_en=list(entry.actions_en),
                why_zh=f"{entry.title_zh}的排序依据是现有 {signal_metric} 加权贡献。",
                why_en=f"{entry.title_en} is prioritized using the existing weighted contribution from {signal_metric}.",
                signal_metric=signal_metric,
                signal_points=signal_points,
                supporting_evidence=[_evidence_ref(item) for item in supporting],
                guidance_ids=list(entry.guidance_ids),
                limitation_zh=ACTION_LIMITATION_ZH,
                limitation_en=ACTION_LIMITATION_EN,
            ))
            derived.extend([
                fact("action_priority_rank", "Action priority rank", priority_rank, grid_id=grid_id, source_component="ACTION_ENGINE", unit="rank", method="DETERMINISTIC_ACTION_PRIORITY_V1"),
                fact("action_family", "Action family", family.value, grid_id=grid_id, source_component="ACTION_ENGINE", method="DETERMINISTIC_ACTION_PRIORITY_V1"),
                fact("action_signal_metric", "Action signal metric", signal_metric, grid_id=grid_id, source_component="ACTION_ENGINE", method="EXISTING_WEIGHTED_CONTRIBUTION_V1"),
                fact("action_signal_points", "Action signal points", signal_points, grid_id=grid_id, source_component="ACTION_ENGINE", unit="points", method="EXISTING_WEIGHTED_CONTRIBUTION_V1"),
            ])
            for guidance_id in entry.guidance_ids:
                derived.append(fact(
                    "action_guidance_ref",
                    "Action guidance reference",
                    guidance_id,
                    grid_id=grid_id,
                    source_component="ACTION_ENGINE",
                    source_ref=ACTION_GUIDANCE_REGISTRY[guidance_id].url,
                    method="CURATED_PUBLIC_GUIDANCE_V1",
                ))

        unique_guidance_ids = list(dict.fromkeys(guidance_ids))
        plan = GridActionPlan(
            grid_id=grid_id,
            risk_score=float(grid["risk_score"]),
            risk_scope=RISK_SCOPE,
            action_cards=cards,
            guidance=[ACTION_GUIDANCE_REGISTRY[item] for item in unique_guidance_ids],
        )
        return ToolResult(
            tool_name="recommend_actions",
            data=plan.model_dump(mode="json"),
            evidence=underlying + derived,
            result_count=len(cards),
        )

    def recommend_for_hotspots(self, limit: int = 5) -> ToolResult:
        if limit < 1 or limit > 10:
            raise ValueError("hotspot action limit must be between 1 and 10")
        hotspots = self.query_service.hotspots(limit)
        evidence = list(hotspots.evidence)
        items: list[HotspotActionItem] = []
        guidance_ids: list[str] = []
        for row in hotspots.data:
            grid_id = row["grid_id"]
            grid = self.query_service.repository.get_grid(grid_id)
            ranked = self.rank_signals({family: float(grid[metric]) for family, metric in SIGNAL_METRICS.items()})
            family, signal_points = ranked[0]
            signal_metric = SIGNAL_METRICS[family]
            entry = ACTION_CATALOG[family]
            guidance_ids.extend(entry.guidance_ids)
            row_facts = [
                item for item in evidence
                if item.grid_id == grid_id and item.metric in {"hotspot_rank", "risk_score", "population_total", "dominant_weighted_contribution"}
            ]
            signal_fact = fact(
                signal_metric,
                "Top action weighted contribution",
                signal_points,
                grid_id=grid_id,
                source_component="RISK_MODEL",
                unit="points",
                method="EXISTING_WEIGHTED_CONTRIBUTION_V1",
            )
            evidence.append(signal_fact)
            evidence.extend([
                fact("action_priority_rank", "Top action priority rank", 1, grid_id=grid_id, source_component="ACTION_ENGINE", unit="rank", method="DETERMINISTIC_ACTION_PRIORITY_V1"),
                fact("action_family", "Top action family", family.value, grid_id=grid_id, source_component="ACTION_ENGINE", method="DETERMINISTIC_ACTION_PRIORITY_V1"),
                fact("action_signal_metric", "Top action signal metric", signal_metric, grid_id=grid_id, source_component="ACTION_ENGINE", method="EXISTING_WEIGHTED_CONTRIBUTION_V1"),
                fact("action_signal_points", "Top action signal points", signal_points, grid_id=grid_id, source_component="ACTION_ENGINE", unit="points", method="EXISTING_WEIGHTED_CONTRIBUTION_V1"),
            ])
            items.append(HotspotActionItem(
                hotspot_rank=int(row["rank"]),
                grid_id=grid_id,
                risk_score=float(row["risk_score"]),
                population_total=float(row["population_total"]),
                dominant_weighted_contribution=str(row["dominant_weighted_contribution"]),
                top_action_family=family,
                top_action_signal_metric=signal_metric,
                top_action_signal_points=signal_points,
                supporting_evidence=[_evidence_ref(item) for item in [*row_facts, signal_fact]],
            ))

        evidence.extend([
            fact("action_catalog_version", "Action catalog version", ACTION_CATALOG_VERSION, source_component="ACTION_ENGINE", method="GROUNDED_ACTION_CATALOG_V1"),
            fact("recommendation_status", "Recommendation status", RECOMMENDATION_STATUS, source_component="ACTION_ENGINE", method="DETERMINISTIC_ACTION_PRIORITY_V1"),
        ])
        for guidance_id in dict.fromkeys(guidance_ids):
            evidence.append(fact(
                "action_guidance_ref",
                "Action guidance reference",
                guidance_id,
                source_component="ACTION_ENGINE",
                source_ref=ACTION_GUIDANCE_REGISTRY[guidance_id].url,
                method="CURATED_PUBLIC_GUIDANCE_V1",
            ))
        unique_guidance_ids = list(dict.fromkeys(guidance_ids))
        overview = HotspotActionOverview(
            items=items,
            guidance=[ACTION_GUIDANCE_REGISTRY[item] for item in unique_guidance_ids],
            limitation_zh=ACTION_LIMITATION_ZH,
            limitation_en=ACTION_LIMITATION_EN,
        )
        return ToolResult(
            tool_name="recommend_actions",
            data=overview.model_dump(mode="json"),
            evidence=evidence,
            result_count=len(items),
        )


def _evidence_ref(item: EvidenceFact) -> ActionEvidenceRef:
    return ActionEvidenceRef(
        evidence_id=item.evidence_id or "",
        metric=item.metric,
        grid_id=item.grid_id,
        value=item.value,
    )
