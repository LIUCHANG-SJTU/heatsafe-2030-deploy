from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EvidenceFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str | None = None
    metric: str
    label: str
    value: Any
    unit: str | None = None
    grid_id: str | None = None
    source_component: str
    source_ref: str
    method: str | None = None
    data_mode: str = "REAL"
    qa_status: str | None = None


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    data: Any
    evidence: list[EvidenceFact] = Field(default_factory=list)
    result_count: int = 0


def fact(
    metric: str,
    label: str,
    value: Any,
    *,
    grid_id: str | None = None,
    source_component: str = "DEMO_METADATA",
    source_ref: str = "heatsafe_demo_v1_2026",
    unit: str | None = None,
    method: str | None = None,
    qa_status: str | None = None,
) -> EvidenceFact:
    return EvidenceFact(
        metric=metric,
        label=label,
        value=value,
        unit=unit,
        grid_id=grid_id,
        source_component=source_component,
        source_ref=source_ref,
        method=method,
        qa_status=qa_status,
    )
