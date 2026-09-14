from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .evidence import ToolResult
from .renderer import DeterministicGroundedRenderer
from .semantic_contract import SemanticIntentContract, SemanticRequirement


SEMANTIC_RENDER_NO_SINGLE_RESULT_COVERS_CONTRACT = "SEMANTIC_RENDER_NO_SINGLE_RESULT_COVERS_CONTRACT"


class SemanticRenderArbitrationError(ValueError):
    pass


@dataclass(frozen=True)
class RenderArbitrationDecision:
    selected_result: ToolResult
    candidate_tools: tuple[str, ...]
    candidate_coverage: tuple[dict[str, Any], ...]
    full_contract_candidates: tuple[str, ...]
    selection_reason: str

    @property
    def used(self) -> bool:
        return len(self.candidate_tools) > 1


class SemanticRenderArbitrator:
    """Select a terminal ToolResult by result-local semantic coverage."""

    def __init__(self, renderer: DeterministicGroundedRenderer, contract: SemanticIntentContract) -> None:
        self.renderer = renderer
        self.contract = contract

    def select(
        self,
        results: Iterable[ToolResult],
        requirement: SemanticRequirement,
        user_text: str,
    ) -> RenderArbitrationDecision | None:
        candidates = [result for result in results if self.renderer.can_render(result, user_text)]
        if not candidates:
            return None

        coverage = [self._coverage(result, requirement, index) for index, result in enumerate(candidates)]
        candidate_tools = tuple(result.tool_name for result in candidates)
        full_indices = [index for index, item in enumerate(coverage) if item["full_contract"]]
        full_tools = tuple(candidates[index].tool_name for index in full_indices)

        if len(candidates) == 1:
            return RenderArbitrationDecision(
                selected_result=candidates[0],
                candidate_tools=candidate_tools,
                candidate_coverage=tuple(coverage),
                full_contract_candidates=full_tools,
                selection_reason="SINGLE_RENDERABLE_RESULT",
            )

        if not requirement.constrained:
            return RenderArbitrationDecision(
                selected_result=candidates[-1],
                candidate_tools=candidate_tools,
                candidate_coverage=tuple(coverage),
                full_contract_candidates=full_tools,
                selection_reason="NO_ACTIVE_SEMANTIC_CONTRACT",
            )

        if full_indices:
            selected_index = max(
                full_indices,
                key=lambda index: (
                    coverage[index]["covered_requirements"],
                    coverage[index]["binding_specificity"],
                    -coverage[index]["execution_order"],
                ),
            )
            return RenderArbitrationDecision(
                selected_result=candidates[selected_index],
                candidate_tools=candidate_tools,
                candidate_coverage=tuple(coverage),
                full_contract_candidates=full_tools,
                selection_reason="SEMANTIC_CONTRACT_FULL_COVERAGE",
            )

        maximum = max(item["covered_requirements"] for item in coverage)
        maximum_indices = [index for index, item in enumerate(coverage) if item["covered_requirements"] == maximum]
        if maximum > 0 and len(maximum_indices) == 1:
            selected_index = maximum_indices[0]
            return RenderArbitrationDecision(
                selected_result=candidates[selected_index],
                candidate_tools=candidate_tools,
                candidate_coverage=tuple(coverage),
                full_contract_candidates=(),
                selection_reason="SEMANTIC_CONTRACT_MAX_COVERAGE",
            )

        raise SemanticRenderArbitrationError(SEMANTIC_RENDER_NO_SINGLE_RESULT_COVERS_CONTRACT)

    def _coverage(self, result: ToolResult, requirement: SemanticRequirement, execution_order: int) -> dict[str, Any]:
        facts = tuple(result.evidence)
        metrics = {item.metric for item in facts}
        completeness = self.contract.evaluate(requirement, facts)
        required_satisfied = sum(slot in metrics for slot in requirement.required)
        any_satisfied = sum(any(slot in metrics for slot in alternatives) for alternatives in requirement.required_any)
        binding_satisfied = requirement.binding is None or completeness.status == "PASS"
        total = len(requirement.required) + len(requirement.required_any) + int(requirement.binding is not None)
        covered = required_satisfied + any_satisfied + int(requirement.binding is not None and binding_satisfied)
        return {
            "tool_name": result.tool_name,
            "execution_order": execution_order,
            "covered_requirements": covered,
            "total_requirements": total,
            "coverage_ratio": round(covered / total, 6) if total else 1.0,
            "missing_slots": list(completeness.missing_slots),
            "binding_specificity": int(requirement.binding is not None and binding_satisfied),
            "full_contract": completeness.status == "PASS",
        }
