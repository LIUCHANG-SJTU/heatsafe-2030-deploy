from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ActionFamily(StrEnum):
    HEAT_EXPOSURE_MITIGATION = "HEAT_EXPOSURE_MITIGATION"
    POPULATION_EXPOSURE_MANAGEMENT = "POPULATION_EXPOSURE_MANAGEMENT"
    VULNERABLE_POPULATION_PROTECTION = "VULNERABLE_POPULATION_PROTECTION"
    ADAPTIVE_CAPACITY_ENHANCEMENT = "ADAPTIVE_CAPACITY_ENHANCEMENT"


class ActionGuidanceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    guidance_id: str
    organization_zh: str
    organization_en: str
    title_zh: str
    title_en: str
    year: int
    section_zh: str
    section_en: str
    url: str

    # Backward-compatible accessors for the M5C internal contract. New public
    # payloads use the explicit bilingual fields above.
    @property
    def organization(self) -> str:
        return self.organization_en

    @property
    def title(self) -> str:
        return self.title_en

    @property
    def section(self) -> str:
        return self.section_en


class ActionEvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = ""
    metric: str
    grid_id: str | None = None
    value: Any


class ActionCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priority_rank: int = Field(ge=1, le=4)
    action_family: ActionFamily
    title_zh: str
    title_en: str
    recommended_actions_zh: list[str] = Field(min_length=1)
    recommended_actions_en: list[str] = Field(min_length=1)
    why_zh: str
    why_en: str
    signal_metric: str
    signal_points: float
    supporting_evidence: list[ActionEvidenceRef]
    guidance_ids: list[str] = Field(min_length=1)
    recommendation_status: str = "DECISION_SUPPORT_HEURISTIC"
    effect_estimate: None = None
    limitation_zh: str
    limitation_en: str


class GridActionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: str = "grid"
    grid_id: str
    risk_score: float
    risk_scope: str
    action_cards: list[ActionCard]
    guidance: list[ActionGuidanceRef]
    recommendation_status: str = "DECISION_SUPPORT_HEURISTIC"


class HotspotActionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hotspot_rank: int = Field(ge=1)
    grid_id: str
    risk_score: float
    population_total: float
    dominant_weighted_contribution: str
    top_action_family: ActionFamily
    top_action_signal_metric: str
    top_action_signal_points: float
    supporting_evidence: list[ActionEvidenceRef]
    recommendation_status: str = "DECISION_SUPPORT_HEURISTIC"
    effect_estimate: None = None


class HotspotActionOverview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: str = "hotspots"
    items: list[HotspotActionItem]
    guidance: list[ActionGuidanceRef]
    recommendation_status: str = "DECISION_SUPPORT_HEURISTIC"
    limitation_zh: str
    limitation_en: str
