from __future__ import annotations

from .evidence import EvidenceFact, ToolResult


class EvidenceLedger:
    """Request-scoped, append-only evidence ID ledger."""

    def __init__(self) -> None:
        self._items: list[EvidenceFact] = []

    def append(self, result: ToolResult) -> ToolResult:
        assigned: list[EvidenceFact] = []
        for item in result.evidence:
            evidence_id = f"E{len(self._items) + 1}"
            fact = item.model_copy(update={"evidence_id": evidence_id})
            self._items.append(fact)
            assigned.append(fact)
        return result.model_copy(update={
            "evidence": assigned,
            "data": _bind_structured_evidence_refs(result.data, assigned),
        })

    def all(self) -> list[EvidenceFact]:
        return list(self._items)

    def for_result(self, result: ToolResult) -> list[EvidenceFact]:
        ids = {item.evidence_id for item in result.evidence}
        return [item for item in self._items if item.evidence_id in ids]


def _bind_structured_evidence_refs(data, evidence: list[EvidenceFact]):
    """Resolve structured evidence refs after request-local IDs are assigned."""
    if isinstance(data, list):
        return [_bind_structured_evidence_refs(item, evidence) for item in data]
    if not isinstance(data, dict):
        return data
    rebound = {
        key: _bind_structured_evidence_refs(value, evidence)
        for key, value in data.items()
    }
    if {"evidence_id", "metric", "value"} <= set(rebound):
        match = next((
            item for item in evidence
            if item.metric == rebound["metric"]
            and item.grid_id == rebound.get("grid_id")
            and item.value == rebound["value"]
        ), None)
        if match is not None:
            rebound["evidence_id"] = match.evidence_id
    return rebound
