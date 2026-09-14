from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EvidenceClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str
    source_ids: list[str] = Field(default_factory=list)
    is_scenario_estimate: bool = False
    causal_language: bool = False


class VerificationReport(BaseModel):
    passed: bool
    missing_evidence: list[str]
    unsupported_claims: list[str]
    scenario_causality_warnings: list[str]


class Verifier:
    """Deterministic guardrails before a future LLM explanation is returned."""

    def verify(self, claims: list[EvidenceClaim]) -> VerificationReport:
        missing_evidence = [claim.claim for claim in claims if not claim.source_ids]
        causality_warnings = [
            claim.claim
            for claim in claims
            if claim.is_scenario_estimate and claim.causal_language
        ]
        unsupported = list(missing_evidence)
        return VerificationReport(
            passed=not missing_evidence and not causality_warnings,
            missing_evidence=missing_evidence,
            unsupported_claims=unsupported,
            scenario_causality_warnings=causality_warnings,
        )

