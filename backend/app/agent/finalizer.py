from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .evidence import EvidenceFact
from .localization import AgentLocale
from .validator import AgentResponseValidator


class GroundedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[str] = Field(default_factory=list)


class GroundedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[GroundedClaim] = Field(min_length=1, max_length=12)
    limitations: list[str] = Field(default_factory=list, max_length=8)


class GroundedFinalizer:
    """Internal finalizer contract; only validated claims may become public text."""

    def __init__(self) -> None:
        self.validator = AgentResponseValidator()

    def finalize(self, answer: GroundedAnswer, evidence: list[EvidenceFact], *, locale: AgentLocale = "zh-CN") -> str:
        by_id = {item.evidence_id: item for item in evidence if item.evidence_id}
        for claim in answer.claims:
            if any(ref not in by_id for ref in claim.evidence_ids):
                raise ValueError("finalizer references unknown evidence")
            claim_evidence = [by_id[ref] for ref in claim.evidence_ids]
            claim_text = _humanize(claim.text, locale) + " " + " ".join(f"[{ref}]" for ref in claim.evidence_ids)
            claim_validation = self.validator.validate(claim_text, claim_evidence)
            if claim_validation.status != "PASS":
                raise ValueError("finalizer output failed validation: " + "; ".join(claim_validation.errors))
        text = "\n".join(f"{_humanize(claim.text, locale)} " + " ".join(f"[{ref}]" for ref in claim.evidence_ids) for claim in answer.claims)
        if answer.limitations:
            text += "\n" + " ".join(_humanize(item, locale) for item in answer.limitations)
        validation = self.validator.validate(text, evidence)
        if validation.status != "PASS":
            raise ValueError("finalizer output failed validation: " + "; ".join(validation.errors))
        return text


def _humanize(text: str, locale: AgentLocale) -> str:
    label = "分析区域内相对风险" if locale == "zh-CN" else "relative risk within the analysis area"
    return text.replace(r"RELATIVE\_WITHIN\_DEMO\_AOI", label).replace("RELATIVE_WITHIN_DEMO_AOI", label)
