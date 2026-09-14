from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

from .config import AgentSettings, agent_settings
from .evidence import EvidenceFact, ToolResult
from .evidence_ledger import EvidenceLedger
from .fallback import DeterministicFallbackResponder
from .finalizer import GroundedAnswer, GroundedFinalizer
from .localization import guard_message, response_language_instruction
from .providers.base import LLMProvider, ToolChoiceMode
from .query_service import HeatSafeQueryService
from .render_arbitration import (
    SEMANTIC_RENDER_NO_SINGLE_RESULT_COVERS_CONTRACT,
    SemanticRenderArbitrationError,
    SemanticRenderArbitrator,
)
from .renderer import DeterministicGroundedRenderer, RENDERING_SOURCE
from .semantic_contract import QueryFieldCanonicalizer, SemanticIntentContract, action_recommendation_scope, compare_mode, selected_ranked_compare_requested
from .semantic_policy import normalize_compare_arguments, query_completeness_errors, query_intent, query_policy_instruction
from .schemas import AgentQueryRequest, AgentQueryResponse, AgentRole, AgentValidation, AgentQualification, CompareGridsInput, GridFilter, MapAction, PublicToolTrace, QueryGridsInput, FilterOperator, MethodologyTopic
from .tools.contracts import finalizer_tool_schema, provider_tool_schemas
from .tools.registry import ToolRegistry
from .tool_capabilities import ToolEvidenceCapabilities
from .tracing import AgentTrace
from .validator import AgentResponseValidator, InjectionGuard, ScenarioScopeGuard


POLICY_VERSION = "M5B_GROUNDED_V1"
PROMPT_PATH = Path(__file__).parent / "prompts/system_v1.txt"
SYSTEM_PROMPT_SHA256 = hashlib.sha256(PROMPT_PATH.read_bytes()).hexdigest()


class GroundedAgent:
    def __init__(self, service: HeatSafeQueryService, provider: LLMProvider | None = None, settings: AgentSettings = agent_settings) -> None:
        self.registry = ToolRegistry(service)
        self.service = service
        self.provider = provider
        self.settings = settings
        self.validator = AgentResponseValidator()
        self.guard = ScenarioScopeGuard()
        self.injection_guard = InjectionGuard()
        self.fallback = DeterministicFallbackResponder()
        self.renderer = DeterministicGroundedRenderer()
        self.semantic_contract = SemanticIntentContract()
        self.render_arbitrator = SemanticRenderArbitrator(self.renderer, self.semantic_contract)
        self.query_field_canonicalizer = QueryFieldCanonicalizer()
        self.tool_evidence_capabilities = ToolEvidenceCapabilities()

    def status(self) -> dict[str, Any]:
        return {"enabled": self.provider is not None, "policy_version": POLICY_VERSION, "provider_kind": getattr(self.provider, "name", self.settings.provider or "not_configured"), "model": getattr(self.provider, "model", self.settings.model or ""), "thinking_mode": getattr(self.provider, "thinking_mode", "") or self.settings.thinking_mode or "provider_default", "max_output_tokens": getattr(self.provider, "max_output_tokens", self.settings.max_output_tokens), "tools": self.registry.names, "scenario_simulation": False, "external_web": False, "data_mode": "REAL", "risk_scope": "RELATIVE_WITHIN_DEMO_AOI"}

    async def answer(self, request: AgentQueryRequest, request_id: str | None = None) -> AgentQueryResponse:
        request_id = request_id or str(uuid.uuid4())
        trace = AgentTrace(request_id)
        latest = next((message.content for message in reversed(request.messages) if message.role == AgentRole.USER), "")
        if request.context.selected_grid_id and not self.service.repository.has_grid(request.context.selected_grid_id):
            raise ValueError("selected_grid_id does not exist in the demo")
        if self.guard.is_scenario_request(latest):
            trace.routing_source = "DETERMINISTIC_GUARD"
            trace.validation_status = "PASS"
            return self._response(request_id, self.fallback.scope(locale=request.context.locale), [], [], [], "SCOPE_LIMITATION", trace, "deterministic", "scope-v1")
        if self.injection_guard.is_injection_request(latest):
            trace.routing_source = "DETERMINISTIC_GUARD"
            trace.validation_status = "PASS"
            answer = guard_message(request.context.locale, "injection")
            return self._response(request_id, answer, [], [], [], "SCOPE_LIMITATION", trace, "deterministic", "security-v1")
        action_scope = action_recommendation_scope(latest)
        explicit_grid_id = _explicit_grid_id(latest)
        if explicit_grid_id and not self.service.repository.has_grid(explicit_grid_id):
            raise ValueError("action grid_id does not exist in the demo")
        if action_scope == "GRID" and not request.context.selected_grid_id and not explicit_grid_id:
            trace.routing_source = "DETERMINISTIC_GUARD"
            trace.validation_status = "PASS"
            answer = guard_message(request.context.locale, "missing_grid")
            return self._response(request_id, answer, [], [], [], "SCOPE_LIMITATION", trace, "deterministic", "action-context-v1")
        if any(token in latest.lower() for token in ["死亡概率", "患病概率", "mortality", "health outcome", "杭州市整体", "杭州全市", "citywide"]):
            trace.routing_source = "DETERMINISTIC_GUARD"
            methodology = self.service.methodology(MethodologyTopic.RISK_SCOPE)
            evidence = _assign_ids(methodology.evidence)
            answer = guard_message(request.context.locale, "risk_scope")
            validation = self.validator.validate(answer, evidence)
            trace.validation_status = validation.status
            return self._response(request_id, answer, evidence, [PublicToolTrace(tool_name=methodology.tool_name, status="completed", result_count=1)], [], "SCOPE_LIMITATION", trace, "deterministic", "scope-v1", validation)
        if any(token in latest for token in ["医疗诊断", "政策优化", "医疗建议"]):
            trace.routing_source = "DETERMINISTIC_GUARD"
            answer = guard_message(request.context.locale, "medical")
            return self._response(request_id, answer, [], [], [], "SCOPE_LIMITATION", trace, "deterministic", "scope-v1")
        if self.provider is not None:
            return await self._provider_answer(request, latest, trace)
        return self._deterministic_answer(request, latest, trace, "PROVIDER_NOT_CONFIGURED")

    def _deterministic_answer(self, request: AgentQueryRequest, latest: str, trace: AgentTrace, reason: str) -> AgentQueryResponse:
        trace.routing_source = "DETERMINISTIC_FALLBACK"
        trace.fallback_used = True
        trace.fallback_reason = reason
        result, actions = self._route(latest, request)
        results = result if isinstance(result, list) else [result]
        evidence = _assign_ids([item for item in results for item in item.evidence])
        traces = [PublicToolTrace(tool_name=item.tool_name, status="completed", result_count=item.result_count) for item in results]
        fallback_answer = self._fallback_answer(latest, results, evidence, request)
        validation_started = time.perf_counter()
        validation = self.validator.validate(fallback_answer, evidence, actions)
        trace.validation_latency_ms += (time.perf_counter() - validation_started) * 1000
        if validation.status != "PASS":
            trace.error_code = trace.error_code or "FALLBACK_VALIDATION_FAILED"
            answer = self._safe_static_answer(results, evidence, request)
            validation = self.validator.validate(answer, evidence, actions)
        else:
            answer = fallback_answer
        trace.validation_status = validation.status
        trace.final_validation_status = validation.status
        trace.tool_execution_count += len(traces)
        trace.tool_calls.extend(item.model_dump() for item in traces)
        return self._response(trace.request_id, answer, evidence, traces, actions, "DETERMINISTIC_FALLBACK", trace, "deterministic", "fallback-v1", validation)

    async def _provider_answer(self, request: AgentQueryRequest, latest: str, trace: AgentTrace) -> AgentQueryResponse:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": PROMPT_PATH.read_text(encoding="utf-8")},
            {"role": "system", "content": response_language_instruction(request.context.locale)},
        ]
        messages.extend({"role": message.role.value, "content": message.content} for message in request.messages)
        messages.append({"role": "system", "content": f"Current UI context: {request.context.model_dump_json()}"})
        requested_query_intent = query_intent(latest, self.service)
        action_grid_id = request.context.selected_grid_id or _explicit_grid_id(latest)
        ranked_grid_id = (
            self.service.resolve_hotspot_rank(2)
            if request.context.selected_grid_id and selected_ranked_compare_requested(latest)
            else None
        )
        semantic_requirement = self.semantic_contract.identify(
            latest,
            selected_grid_id=action_grid_id,
            ranked_grid_id=ranked_grid_id,
            query_intent=requested_query_intent,
        )
        trace.semantic_intent = semantic_requirement.intent
        trace.compare_mode = compare_mode(latest).value
        policy_instruction = query_policy_instruction(requested_query_intent)
        if policy_instruction:
            messages.append({"role": "system", "content": policy_instruction})
        public_tools = provider_tool_schemas()
        finalization_tools = [*public_tools, finalizer_tool_schema()]
        results: list[ToolResult] = []
        ledger = EvidenceLedger()
        public_traces: list[PublicToolTrace] = []
        actions: list[MapAction] = []
        repair_budget = 1
        evidence_completion_budget = 1
        agent_state = "PLANNING"
        first_turn = True
        force_finalizer_repair = False
        provider_name = getattr(self.provider, "name", "provider")
        model_name = getattr(self.provider, "model", "")
        finalizer = GroundedFinalizer()
        while trace.provider_turn_count < self.settings.max_tool_steps + 1:
            is_completion_turn = agent_state == "EVIDENCE_COMPLETION"
            trace.agent_state = agent_state
            active_tools = public_tools if agent_state == "PLANNING" else finalization_tools
            if is_completion_turn:
                missing_slots = list(trace.semantic_missing_evidence_slots)
                candidate_tools = self.tool_evidence_capabilities.tools_covering_all(missing_slots)
                trace.semantic_completion_missing_slots = missing_slots
                trace.semantic_completion_candidate_tools = candidate_tools
                trace.semantic_completion_candidate_count = len(candidate_tools)
                trace.semantic_completion_capability_filter_used = True
                trace.terminal_action_gated = True
                trace.terminal_action_gate_reason = "SEMANTIC_EVIDENCE_INCOMPLETE"
                trace.semantic_completion_tool_required = True
                trace.semantic_completion_tool_choice_mode = "REQUIRED"
                if not candidate_tools:
                    trace.error_code = "SEMANTIC_COMPLETION_NO_CAPABLE_TOOL"
                    trace.semantic_contract_status = "FAIL_INCOMPLETE"
                    return self._deterministic_answer(request, latest, trace, "SEMANTIC_COMPLETION_NO_CAPABLE_TOOL")
                trace.semantic_completion_provider_attempts += 1
                active_tools = [
                    schema
                    for schema in public_tools
                    if str(schema.get("function", {}).get("name")) in candidate_tools
                ]
            provider_started = time.perf_counter()
            trace.provider_attempt_count += 1
            try:
                metadata = {"request_id": trace.request_id}
                if force_finalizer_repair:
                    metadata["tool_choice"] = {"type": "function", "function": {"name": "submit_grounded_answer"}}
                elif agent_state == "PLANNING":
                    metadata["tool_choice_mode"] = ToolChoiceMode.AUTO
                elif is_completion_turn:
                    metadata["tool_choice_mode"] = ToolChoiceMode.REQUIRED
                turn = await self.provider.complete(messages, active_tools, metadata)
            except Exception as error:
                trace.provider_latency_ms += (time.perf_counter() - provider_started) * 1000
                timeout = isinstance(error, TimeoutError) or "timeout" in type(error).__name__.lower()
                trace.error_code = "PROVIDER_TIMEOUT" if timeout else "PROVIDER_UNAVAILABLE"
                return self._deterministic_answer(request, latest, trace, "PROVIDER_TIMEOUT" if timeout else "PROVIDER_ERROR")
            trace.provider_turn_count += 1
            trace.provider_latency_ms += (time.perf_counter() - provider_started) * 1000
            trace.provider_finish_reasons.append(turn.finish_reason or "UNKNOWN")
            completion_tokens = turn.usage.get("completion_tokens", 0) if isinstance(turn.usage, dict) else 0
            if isinstance(completion_tokens, int):
                trace.provider_completion_tokens += completion_tokens
            model_name = turn.model or model_name
            calls = [_with_call_id(call, index) for index, call in enumerate(turn.tool_calls or [], start=1)]
            names = [str(call.get("name")) for call in calls if call.get("name")]
            finalizer_call = next((call for call in calls if call.get("name") == "submit_grounded_answer"), None)
            public_calls = [call for call in calls if call.get("name") != "submit_grounded_answer"]
            if is_completion_turn:
                trace.semantic_completion_public_tool_called = bool(public_calls)
                trace.semantic_completion_selected_tool = str(public_calls[0].get("name")) if public_calls else None
                if not public_calls:
                    trace.error_code = "SEMANTIC_COMPLETION_NO_TOOL_CALL"
                    trace.semantic_contract_status = "FAIL_INCOMPLETE"
                    return self._deterministic_answer(request, latest, trace, "SEMANTIC_COMPLETION_NO_TOOL_CALL")
                selected_tools = [str(call.get("name", "")) for call in public_calls]
                if any(name not in trace.semantic_completion_candidate_tools for name in selected_tools):
                    trace.error_code = "SEMANTIC_COMPLETION_INELIGIBLE_TOOL"
                    trace.semantic_contract_status = "FAIL_INCOMPLETE"
                    return self._deterministic_answer(request, latest, trace, "SEMANTIC_COMPLETION_INELIGIBLE_TOOL")
                selected_capability = self.tool_evidence_capabilities.for_tool(selected_tools[0])
                trace.semantic_completion_selected_tool_capabilities = selected_capability.as_dict()
            if first_turn:
                # Routing qualification measures public HeatSafe tool selection;
                # the finalizer is a separate protocol step.
                trace.first_attempt_tool_calls = [str(call.get("name")) for call in public_calls if call.get("name")]
                first_turn = False
            trace.provider_tool_calls.extend(names)
            semantic_errors: list[str] = []
            if requested_query_intent.constrained:
                query_calls = [call for call in public_calls if call.get("name") == "query_grids"]
                for call in query_calls:
                    try:
                        query_arguments = _call_arguments(call)
                        query_arguments, canonicalized = self.query_field_canonicalizer.canonicalize(query_arguments)
                        if canonicalized:
                            trace.tool_argument_canonicalization_used = True
                            trace.canonicalized_fields.extend(item for item in canonicalized if item not in trace.canonicalized_fields)
                        query_request = QueryGridsInput.model_validate(query_arguments)
                        semantic_errors.extend(query_completeness_errors(query_request, requested_query_intent))
                    except Exception as error:
                        semantic_errors.append(f"invalid query arguments: {type(error).__name__}: {str(error)[:240]}")
                if query_calls:
                    trace.query_intent_completeness_status = "FAIL" if semantic_errors else "PASS"
                    trace.query_intent_completeness_errors = semantic_errors[:20]
            if semantic_errors:
                # Preserve the OpenAI tool-call wire contract even though the
                # incomplete call is rejected before any data tool executes.
                wire_calls = public_calls if (finalizer_call is not None and public_calls) else calls
                messages.append({"role": "assistant", "content": turn.text, "tool_calls": wire_calls})
                for call in public_calls:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.get("id", call.get("name", "tool")),
                        "content": json.dumps({"error": "QUERY_INTENT_INCOMPLETE", "details": semantic_errors}, ensure_ascii=False),
                    })
                if repair_budget:
                    repair_budget -= 1
                    trace.validation_repair_used = True
                    trace.validation_repair_count += 1
                    force_finalizer_repair = False
                    agent_state = "PLANNING"
                    messages.append({
                        "role": "system",
                        "content": (
                            "The query tool call was not executed because it omitted an explicit user constraint. "
                            "Call query_grids once with every required filter. "
                            + (policy_instruction or "")
                            + " Errors: "
                            + "; ".join(semantic_errors)
                        ),
                    })
                    continue
                trace.error_code = "QUERY_INTENT_INCOMPLETE"
                return self._deterministic_answer(request, latest, trace, "QUERY_INTENT_REPAIR_EXHAUSTED")
            if calls:
                # If a provider bundled an early finalizer with public calls,
                # keep only the calls that receive tool responses on the wire.
                # An unmatched assistant tool call is invalid for OpenAI-style
                # protocols and would poison the next request.
                wire_calls = public_calls if (finalizer_call is not None and public_calls) else calls
                messages.append({"role": "assistant", "content": turn.text, "tool_calls": wire_calls})
                for call in public_calls:
                    name = str(call.get("name", ""))
                    try:
                        arguments = _call_arguments(call)
                        if name == "query_grids":
                            arguments, canonicalized = self.query_field_canonicalizer.canonicalize(arguments)
                            if canonicalized:
                                trace.tool_argument_canonicalization_used = True
                                trace.canonicalized_fields.extend(item for item in canonicalized if item not in trace.canonicalized_fields)
                        if name == "compare_grids":
                            arguments, normalized = normalize_compare_arguments(arguments, request, latest, self.service)
                            trace.argument_normalization_used = trace.argument_normalization_used or normalized
                        if name == "recommend_actions":
                            arguments, normalized = _normalize_action_arguments(arguments, action_grid_id)
                            trace.argument_normalization_used = trace.argument_normalization_used or normalized
                        tool_started = time.perf_counter()
                        result = self.registry.execute(name, arguments)
                        trace.tool_latency_ms += (time.perf_counter() - tool_started) * 1000
                        trace.tool_execution_count += 1
                        assigned_result = ledger.append(result)
                        results.append(assigned_result)
                        public_traces.append(PublicToolTrace(tool_name=name, status="completed", result_count=assigned_result.result_count))
                        actions.extend(self._actions_for_result(assigned_result, request))
                        # OpenAI-compatible tool messages require role,
                        # tool_call_id and content. Some providers reject the
                        # legacy optional `name` field on this message.
                        messages.append({"role": "tool", "tool_call_id": call.get("id", name), "content": json.dumps({"data": _provider_data(name, assigned_result.data), "evidence": [item.model_dump() for item in assigned_result.evidence]}, ensure_ascii=False)})
                        citation_instruction = _citation_instruction(assigned_result)
                        if citation_instruction:
                            messages.append({"role": "system", "content": citation_instruction})
                    except Exception as error:
                        if is_completion_turn:
                            trace.error_code = "SEMANTIC_EVIDENCE_INCOMPLETE"
                            trace.semantic_contract_status = "FAIL_INCOMPLETE"
                            return self._deterministic_answer(request, latest, trace, "SEMANTIC_EVIDENCE_INCOMPLETE")
                        trace.error_code = "TOOL_EXECUTION_ERROR"
                        trace.fallback_reason = f"{type(error).__name__}:{str(error)[:160]}"
                        return self._deterministic_answer(request, latest, trace, f"TOOL_ROUTING_ERROR:{type(error).__name__}:{str(error)[:160]}")
                completeness = self.semantic_contract.evaluate(semantic_requirement, ledger.all())
                trace.semantic_contract_status = completeness.status
                trace.semantic_missing_evidence_slots = list(completeness.missing_slots)
                if public_calls and completeness.status != "PASS":
                    if evidence_completion_budget:
                        evidence_completion_budget -= 1
                        trace.evidence_completion_used = True
                        trace.evidence_completion_count += 1
                        trace.semantic_completion_used = True
                        force_finalizer_repair = False
                        agent_state = "EVIDENCE_COMPLETION"
                        messages.append({
                            "role": "system",
                            "content": (
                                "The user request still requires these Evidence slots: "
                                + ", ".join(completeness.missing_slots)
                                + ". Call an available public HeatSafe tool that can provide the missing evidence. "
                                "Do not answer yet and do not call submit_grounded_answer."
                            ),
                        })
                        continue
                    trace.error_code = "SEMANTIC_EVIDENCE_INCOMPLETE"
                    return self._deterministic_answer(request, latest, trace, "SEMANTIC_EVIDENCE_INCOMPLETE")
                try:
                    arbitration = self.render_arbitrator.select(results, semantic_requirement, latest)
                except SemanticRenderArbitrationError:
                    trace.error_code = SEMANTIC_RENDER_NO_SINGLE_RESULT_COVERS_CONTRACT
                    trace.terminal_render_arbitration_used = True
                    trace.terminal_render_selection_reason = SEMANTIC_RENDER_NO_SINGLE_RESULT_COVERS_CONTRACT
                    return self._deterministic_answer(
                        request,
                        latest,
                        trace,
                        SEMANTIC_RENDER_NO_SINGLE_RESULT_COVERS_CONTRACT,
                    )
                renderable_result = arbitration.selected_result if arbitration is not None else None
                if arbitration is not None:
                    trace.terminal_render_arbitration_used = arbitration.used
                    trace.terminal_render_candidate_tools = list(arbitration.candidate_tools)
                    trace.terminal_render_candidate_coverage = list(arbitration.candidate_coverage)
                    trace.terminal_render_full_contract_candidates = list(arbitration.full_contract_candidates)
                    trace.terminal_render_selected_tool = arbitration.selected_result.tool_name
                    trace.terminal_render_selection_reason = arbitration.selection_reason
                if public_calls and renderable_result is not None:
                    trace.agent_state = "READY_TO_FINALIZE"
                    evidence = ledger.all()
                    try:
                        grounded_result = renderable_result.model_copy(update={"evidence": evidence})
                        answer = self.renderer.render(
                            grounded_result,
                            latest,
                            request.context.selected_grid_id,
                            locale=request.context.locale,
                        )
                        validation_started = time.perf_counter()
                        validation = self.validator.validate(answer, evidence, actions)
                        trace.validation_latency_ms += (time.perf_counter() - validation_started) * 1000
                        if validation.status != "PASS":
                            raise ValueError("renderer validation failed: " + "; ".join(validation.errors))
                    except Exception as error:
                        trace.error_code = "GROUNDED_RENDERER_FAILED"
                        trace.last_provider_validation_errors = [str(error)[:500]]
                        return self._deterministic_answer(request, latest, trace, "GROUNDED_RENDERER_FAILED")
                    trace.routing_source = "PROVIDER"
                    trace.rendering_source = RENDERING_SOURCE
                    trace.validation_status = "PASS"
                    trace.final_validation_status = "PASS"
                    if finalizer_call is not None:
                        trace.early_finalizer_deferred = True
                    return self._response(trace.request_id, answer, evidence, public_traces, actions, "GROUNDED", trace, provider_name, model_name, validation)
                if public_calls:
                    agent_state = "READY_TO_FINALIZE"
                # A provider cannot ground a finalizer against a tool result it
                # received in the same response. Defer that call and require a
                # subsequent provider turn after the tool messages are visible.
                if finalizer_call is not None and public_calls:
                    trace.early_finalizer_deferred = True
                    messages.append({"role": "system", "content": "Public tool results are now available. Produce submit_grounded_answer only in a subsequent turn and cite the returned evidence IDs."})
                    continue
                if finalizer_call is not None:
                    evidence = ledger.all()
                    completeness = self.semantic_contract.evaluate(semantic_requirement, evidence)
                    trace.semantic_contract_status = completeness.status
                    trace.semantic_missing_evidence_slots = list(completeness.missing_slots)
                    if completeness.status != "PASS":
                        trace.error_code = "SEMANTIC_EVIDENCE_INCOMPLETE"
                        return self._deterministic_answer(request, latest, trace, "SEMANTIC_EVIDENCE_INCOMPLETE")
                    try:
                        arguments = finalizer_call.get("arguments", {})
                        if isinstance(arguments, str):
                            arguments = json.loads(arguments or "{}")
                        grounded = GroundedAnswer.model_validate(arguments)
                        answer = finalizer.finalize(grounded, evidence, locale=request.context.locale)
                        validation_started = time.perf_counter()
                        validation = self.validator.validate(answer, evidence, actions)
                        validation = self._validate_answer_completeness(latest, answer, results, evidence, validation)
                        trace.validation_latency_ms += (time.perf_counter() - validation_started) * 1000
                        if trace.first_attempt_validation_status == "NOT_RUN":
                            trace.first_attempt_validation_status = validation.status
                            trace.first_attempt_validation_errors = list(validation.errors)
                        if validation.status == "PASS":
                            trace.routing_source = "PROVIDER"
                            trace.validation_status = "PASS"
                            trace.final_validation_status = "PASS"
                            trace.validation_repair_success = trace.validation_repair_used
                            return self._response(trace.request_id, answer, evidence, public_traces, actions, "GROUNDED", trace, provider_name, model_name, validation)
                        raise ValueError("finalizer validation failed: " + "; ".join(validation.errors))
                    except Exception as error:
                        trace.last_provider_validation_errors = [str(error)[:500]]
                        if trace.first_attempt_validation_status == "NOT_RUN":
                            trace.first_attempt_validation_status = "FAIL"
                            trace.first_attempt_validation_errors = [str(error)[:500]]
                        if repair_budget:
                            repair_budget -= 1
                            trace.validation_repair_used = True
                            trace.validation_repair_count += 1
                            force_finalizer_repair = True
                            messages.append({
                                "role": "system",
                                "content": (
                                    "Repair the grounded answer using only the returned evidence. "
                                    "You must call submit_grounded_answer, with no prose answer and no public tool calls. "
                                    "Every numeric token in each claim must exactly match a cited evidence value "
                                    "(do not write a bare 100 for a 1.0 fraction; write 1.0 or 100% only when the cited fact supports it). "
                                    "Every claim text must be a non-empty, concise Chinese sentence. "
                                    + _repair_focus(results)
                                    + f"Validation errors: {error}. Valid evidence IDs: {', '.join(item.evidence_id or '' for item in ledger.all())}. Evidence map: "
                                    + json.dumps([item.model_dump() for item in ledger.all()], ensure_ascii=False)
                                ),
                            })
                            continue
                        trace.error_code = "FINALIZER_VALIDATION_FAILED"
                        return self._deterministic_answer(request, latest, trace, "VALIDATION_REPAIR_EXHAUSTED")
                continue
            if turn.text:
                evidence = ledger.all()
                completeness = self.semantic_contract.evaluate(semantic_requirement, evidence)
                trace.semantic_contract_status = completeness.status
                trace.semantic_missing_evidence_slots = list(completeness.missing_slots)
                if completeness.status != "PASS":
                    trace.error_code = "SEMANTIC_EVIDENCE_INCOMPLETE"
                    return self._deterministic_answer(request, latest, trace, "SEMANTIC_EVIDENCE_INCOMPLETE")
                validation_started = time.perf_counter()
                validation = self.validator.validate(turn.text, evidence, actions)
                validation = self._validate_answer_completeness(latest, turn.text, results, evidence, validation)
                trace.validation_latency_ms += (time.perf_counter() - validation_started) * 1000
                if trace.first_attempt_validation_status == "NOT_RUN":
                    trace.first_attempt_validation_status = validation.status
                    trace.first_attempt_validation_errors = list(validation.errors)
                if validation.status != "PASS":
                    trace.last_provider_validation_errors = list(validation.errors)
                if validation.status == "PASS" and results:
                    trace.routing_source = "PROVIDER"
                    trace.validation_status = "PASS"
                    trace.final_validation_status = "PASS"
                    trace.validation_repair_success = trace.validation_repair_used
                    return self._response(trace.request_id, turn.text, evidence, public_traces, actions, "GROUNDED", trace, provider_name, model_name, validation)
                if repair_budget:
                    repair_budget -= 1
                    trace.validation_repair_used = True
                    trace.validation_repair_count += 1
                    force_finalizer_repair = True
                    agent_state = "READY_TO_FINALIZE"
                    messages.append({
                        "role": "system",
                        "content": (
                            "Your draft failed validation. Call submit_grounded_answer only, using exact evidence IDs and values "
                            "from the tool result. Every claim text must be a non-empty concise Chinese sentence. Do not add any unsupported numeric token. "
                            + _repair_focus(results)
                            + "Errors: "
                            + ", ".join(validation.errors)
                            + ". Evidence map: "
                            + json.dumps([item.model_dump() for item in ledger.all()], ensure_ascii=False)
                            + ". Valid evidence IDs: "
                            + ", ".join(item.evidence_id or "" for item in ledger.all())
                        ),
                    })
                    continue
                return self._deterministic_answer(request, latest, trace, "VALIDATION_REPAIR_EXHAUSTED")
            if results and repair_budget:
                repair_budget -= 1
                trace.validation_repair_used = True
                trace.validation_repair_count += 1
                force_finalizer_repair = not any(token in latest for token in ("比较", "区别", "compare", "difference", "第二名"))
                agent_state = "READY_TO_FINALIZE" if force_finalizer_repair else "PLANNING"
                messages.append({
                    "role": "system",
                    "content": (
                        "The previous response was empty after a tool result. "
                        + ("Call submit_grounded_answer now, with one or more grounded claims using only the returned evidence IDs and values. Do not call a public tool again and do not return prose outside the finalizer. " if force_finalizer_repair else "Continue the requested comparison by selecting the next required public tool; do not return an empty response. ")
                        + "Evidence map: "
                        + json.dumps([item.model_dump() for item in ledger.all()], ensure_ascii=False)
                        + ". Valid evidence IDs: "
                        + ", ".join(item.evidence_id or "" for item in ledger.all())
                    ),
                })
                continue
            empty_reason = "PROVIDER_OUTPUT_TRUNCATED" if turn.finish_reason == "length" else "EMPTY_PROVIDER_RESPONSE"
            return self._deterministic_answer(request, latest, trace, empty_reason)
        return self._deterministic_answer(request, latest, trace, "MAX_PROVIDER_STEPS")

    @staticmethod
    def _actions_for_result(result: ToolResult, request: AgentQueryRequest) -> list[MapAction]:
        rows = result.data if isinstance(result.data, list) else result.data.get("grids", []) if isinstance(result.data, dict) else []
        ids = [row.get("grid_id") for row in rows if isinstance(row, dict) and row.get("grid_id")]
        if result.tool_name in {"list_hotspots", "query_grids"} and ids:
            return [MapAction(action="highlight_grids", grid_ids=ids[:20])]
        if result.tool_name in {"inspect_grid", "explain_risk"} and request.context.selected_grid_id:
            return [MapAction(action="select_grid", grid_ids=[request.context.selected_grid_id])]
        return []

    def _route(self, text: str, request: AgentQueryRequest) -> tuple[ToolResult | list[ToolResult], list[MapAction]]:
        lower = text.lower()
        selected = request.context.selected_grid_id
        action_scope = action_recommendation_scope(text)
        if action_scope == "HOTSPOTS":
            result = self.registry.action_service.recommend_for_hotspots(5)
            return result, [MapAction(action="highlight_grids", grid_ids=[item["grid_id"] for item in result.data["items"]])]
        if action_scope == "GRID" and selected:
            result = self.registry.action_service.recommend_for_grid(selected)
            return result, [MapAction(action="select_grid", grid_ids=[selected])]
        if any(token in text for token in ["这里", "这个格子", "this grid"]) and not selected:
            return self.service.summary(), []
        if any(token in text for token in ["比较", "区别", "不同", "compare", "difference"]) or ("哪个热点" in text and "人口" in text):
            ids = [selected] if selected else []
            if any(token in text for token in ("第二名", "第二", "次高")) or any(token in lower for token in ("second", "top2", "top 2")):
                rank_two = self.service.resolve_hotspot_rank(2)
                if rank_two not in ids:
                    ids.append(rank_two)
            else:
                ids += [row["grid_id"] for row in self.service.hotspots(2).data if row["grid_id"] not in ids]
            return self.service.compare(CompareGridsInput(grid_ids=ids[:2])), [MapAction(action="select_grid", grid_ids=[ids[0]])] if ids else []
        if any(token in lower for token in ["top", "热点", "最高", "hotspot"]):
            result = self.service.hotspots(3)
            return result, [MapAction(action="highlight_grids", grid_ids=[row["grid_id"] for row in result.data])]
        if any(token in text for token in ["筛", "找出", "高暴露", "高人口暴露", "低绿地", "绿地较好", "低暴露", "高绿地", "有人口", "高风险", "排序", "query", "filter", "high risk", "low green", "good green"]):
            intent = query_intent(text, self.service)
            filters = list(intent.filters) or [GridFilter(field="analysis_status", op=FilterOperator.EQ, value="ANALYZABLE_LAND")]
            result = self.service.query(QueryGridsInput(filters=filters, limit=10))
            return result, [MapAction(action="highlight_grids", grid_ids=[row["grid_id"] for row in result.data])]
        if selected and "水域" in text and "风险" in text:
            return self.service.explain(selected), [MapAction(action="select_grid", grid_ids=[selected])]
        if any(token in text for token in ["数据模式", "模型状态"]):
            return self.service.summary(), []
        if any(token in text for token in ["方法", "公式", "ERA5", "数据", "水域", "阈值", "限制", "边界", "vulnerability", "Vulnerability", "exposure", "Exposure", "adaptive", "适应能力", "脆弱", "WorldPop", "Landsat", "Sentinel", "绿地为什么", "为什么绿地"]):
            topic = "era5" if "era5" in lower else "risk_formula" if any(token in text for token in ["公式", "formula", "模型"]) else "overview"
            return self.service.methodology(MethodologyTopic(topic)), []
        if selected and any(token in text for token in ["检查", "质量", "查看", "inspect"]) or (selected and "是多少" in text):
            return self.service.inspect(selected), [MapAction(action="select_grid", grid_ids=[selected])]
        if selected:
            return self.service.explain(selected), [MapAction(action="select_grid", grid_ids=[selected])]
        return self.service.summary(), []

    def _fallback_answer(self, text: str, results: list[ToolResult], evidence: list[EvidenceFact], request: AgentQueryRequest) -> str:
        if results and results[-1].tool_name == "explain_risk":
            return self.fallback.grid_explanation(results[-1].data, evidence, locale=request.context.locale)
        if results and results[-1].tool_name == "get_demo_summary":
            return self.fallback.summary(results[-1].data, evidence, locale=request.context.locale)
        if results and results[-1].tool_name == "compare_grids":
            grounded = results[-1].model_copy(update={"evidence": evidence})
            return self.renderer.render(grounded, text, request.context.selected_grid_id, locale=request.context.locale)
        if results and results[-1].tool_name == "query_grids":
            grounded = results[-1].model_copy(update={"evidence": evidence})
            return self.renderer.render(grounded, text, request.context.selected_grid_id, locale=request.context.locale)
        if results and results[-1].tool_name == "recommend_actions":
            grounded = results[-1].model_copy(update={"evidence": evidence})
            return self.renderer.render(grounded, text, request.context.selected_grid_id, locale=request.context.locale)
        thresholds = [item for item in evidence if item.metric == "query_threshold"]
        threshold_text = "".join(f"{item.label}={item.value} [{item.evidence_id}]。" for item in thresholds)
        if request.context.locale == "en":
            threshold_en = "; ".join(f"{item.label}={item.value} [{item.evidence_id}]" for item in thresholds)
            return "The HeatSafe REAL-data lookup is complete; the evidence below contains the returned grids." + (f" Relative terms use these grounded thresholds: {threshold_en}." if threshold_en else "") + " " + " ".join(f"[{item.evidence_id}]" for item in evidence[:3])
        return "已根据 HeatSafe REAL 数据完成检索，结果和可定位格网见下方 Evidence。" + (f"这里将‘高/低’解释为筛选阈值：{threshold_text}" if threshold_text else "") + " " + " ".join(f"[{item.evidence_id}]" for item in evidence[:3])

    def _validate_answer_completeness(
        self,
        latest: str,
        answer: str,
        results: list[ToolResult],
        evidence: list[EvidenceFact],
        validation: AgentValidation,
    ) -> AgentValidation:
        intent = query_intent(latest, self.service)
        if not intent.constrained or not results or results[-1].tool_name != "query_grids":
            return validation
        errors = list(validation.errors)
        rows = results[-1].data if isinstance(results[-1].data, list) else []
        for row in rows[:3]:
            grid_id = row.get("grid_id")
            if grid_id and grid_id not in answer:
                errors.append(f"query answer missing top result grid: {grid_id}")
            for field in ("exposure_score", "green_fraction_land"):
                value = row.get(field)
                if value is not None and not _contains_numeric_value(answer, value):
                    errors.append(f"query answer missing {field} for {grid_id}")
        total = next((item for item in evidence if item.metric == "query_total_match_count"), None)
        if total is not None and not _contains_numeric_value(answer, total.value):
            errors.append("query answer missing total match count")
        return AgentValidation(status="PASS" if not errors else "FAIL", errors=errors)

    def _safe_static_answer(self, results: list[ToolResult], evidence: list[EvidenceFact], request: AgentQueryRequest) -> str:
        return self._fallback_answer("", results, evidence, request)

    @staticmethod
    def _response(request_id: str, answer: str, evidence: list[EvidenceFact], traces: list[PublicToolTrace], actions: list[MapAction], mode: str, trace: AgentTrace, provider: str, model: str, validation: AgentValidation | None = None) -> AgentQueryResponse:
        final_validation = validation or AgentValidation(status="PASS")
        trace.final_validation_status = final_validation.status
        if not trace.routing_source:
            trace.routing_source = "DETERMINISTIC_GUARD" if mode == "SCOPE_LIMITATION" else "DETERMINISTIC_FALLBACK"
        if not trace.rendering_source:
            trace.rendering_source = "PROVIDER_FINALIZER" if mode == "GROUNDED" else "DETERMINISTIC_GUARD" if mode == "SCOPE_LIMITATION" else "DETERMINISTIC_FALLBACK"
        trace.validation_status = final_validation.status
        trace_data = trace.finish()
        qualification = AgentQualification(
            routing_source=trace_data["routing_source"],
            rendering_source=trace_data["rendering_source"],
            provider_attempt_count=trace_data["provider_attempt_count"],
            provider_turn_count=trace_data["provider_turn_count"],
            provider_tool_calls=trace_data["provider_tool_calls"],
            provider_finish_reasons=trace_data["provider_finish_reasons"],
            provider_completion_tokens=trace_data["provider_completion_tokens"],
            tool_execution_count=trace_data["tool_execution_count"],
            first_attempt_tool_calls=trace_data["first_attempt_tool_calls"],
            first_attempt_validation_status=trace_data["first_attempt_validation_status"],
            first_attempt_validation_errors=trace_data["first_attempt_validation_errors"],
            last_provider_validation_errors=trace_data["last_provider_validation_errors"],
            validation_repair_used=trace_data["validation_repair_used"],
            validation_repair_count=trace_data["validation_repair_count"],
            validation_repair_success=trace_data["validation_repair_success"],
            early_finalizer_deferred=trace_data["early_finalizer_deferred"],
            argument_normalization_used=trace_data["argument_normalization_used"],
            tool_argument_canonicalization_used=trace_data["tool_argument_canonicalization_used"],
            canonicalized_fields=trace_data["canonicalized_fields"],
            semantic_intent=trace_data["semantic_intent"],
            semantic_contract_status=trace_data["semantic_contract_status"],
            semantic_missing_evidence_slots=trace_data["semantic_missing_evidence_slots"],
            evidence_completion_used=trace_data["evidence_completion_used"],
            evidence_completion_count=trace_data["evidence_completion_count"],
            semantic_completion_used=trace_data["semantic_completion_used"],
            semantic_completion_provider_attempts=trace_data["semantic_completion_provider_attempts"],
            terminal_action_gated=trace_data["terminal_action_gated"],
            terminal_action_gate_reason=trace_data["terminal_action_gate_reason"],
            agent_state=trace_data["agent_state"],
            semantic_completion_tool_required=trace_data["semantic_completion_tool_required"],
            semantic_completion_tool_choice_mode=trace_data["semantic_completion_tool_choice_mode"],
            semantic_completion_public_tool_called=trace_data["semantic_completion_public_tool_called"],
            semantic_completion_selected_tool=trace_data["semantic_completion_selected_tool"],
            semantic_completion_missing_slots=trace_data["semantic_completion_missing_slots"],
            semantic_completion_candidate_tools=trace_data["semantic_completion_candidate_tools"],
            semantic_completion_candidate_count=trace_data["semantic_completion_candidate_count"],
            semantic_completion_capability_filter_used=trace_data["semantic_completion_capability_filter_used"],
            semantic_completion_selected_tool_capabilities=trace_data["semantic_completion_selected_tool_capabilities"],
            terminal_render_arbitration_used=trace_data["terminal_render_arbitration_used"],
            terminal_render_candidate_tools=trace_data["terminal_render_candidate_tools"],
            terminal_render_candidate_coverage=trace_data["terminal_render_candidate_coverage"],
            terminal_render_full_contract_candidates=trace_data["terminal_render_full_contract_candidates"],
            terminal_render_selected_tool=trace_data["terminal_render_selected_tool"],
            terminal_render_selection_reason=trace_data["terminal_render_selection_reason"],
            compare_mode=trace_data["compare_mode"],
            query_intent_completeness_status=trace_data["query_intent_completeness_status"],
            query_intent_completeness_errors=trace_data["query_intent_completeness_errors"],
            fallback_used=trace_data["fallback_used"],
            fallback_reason=trace_data["fallback_reason"],
            error_code=trace_data["error_code"],
            final_validation_status=trace_data["final_validation_status"],
            provider_latency_ms=trace_data["provider_latency_ms"],
            tool_latency_ms=trace_data["tool_latency_ms"],
            validation_latency_ms=trace_data["validation_latency_ms"],
            total_latency_ms=trace_data["total_latency_ms"],
            provider_result="PASS" if mode == "GROUNDED" else "FAIL" if trace.provider_attempt_count else "NOT_RUN",
            user_visible_result="GROUNDED" if mode == "GROUNDED" else "SAFE_FALLBACK" if mode == "DETERMINISTIC_FALLBACK" else "SCOPE_LIMITATION",
        )
        return AgentQueryResponse(request_id=request_id, answer=answer, evidence=[item.model_dump() for item in evidence], tool_trace=traces, map_actions=actions, validation=final_validation, answer_mode=mode, provider=provider, model=model, latency_ms=trace_data["total_latency_ms"], qualification=qualification)


def _assign_ids(items: list[EvidenceFact]) -> list[EvidenceFact]:
    return [item.model_copy(update={"evidence_id": f"E{index}"}) for index, item in enumerate(items, start=1)]


def _with_call_id(call: dict[str, Any], index: int) -> dict[str, Any]:
    """Ensure every tool call has a stable non-null ID for the next wire turn."""
    normalized = dict(call)
    normalized["id"] = call.get("id") or f"tool-call-{index}"
    return normalized


def _call_arguments(call: dict[str, Any]) -> dict[str, Any]:
    arguments = call.get("arguments", {})
    if isinstance(arguments, str):
        arguments = json.loads(arguments or "{}")
    if not isinstance(arguments, dict):
        raise ValueError("tool arguments must be an object")
    return arguments


def _comparison_answer(result: ToolResult, evidence: list[EvidenceFact]) -> str:
    data = result.data if isinstance(result.data, dict) else {}
    grids = data.get("grids", [])
    if len(grids) < 2:
        return "没有足够的真实格网证据完成比较。"
    reference, compared = grids[0], grids[1]
    delta = next((item for item in evidence if item.metric == "risk_delta" and item.grid_id == compared.get("grid_id")), None)
    scores = {item.grid_id: item for item in evidence if item.metric == "risk_score" and item.grid_id}
    parts = [f"已比较格网 {reference['grid_id']} 与 {compared['grid_id']}。"]
    if delta is not None:
        parts.append(f"第二个格网相对当前格网的风险分差为 {delta.value} [{delta.evidence_id}]。")
    for grid in (reference, compared):
        score = scores.get(grid.get("grid_id"))
        if score is not None:
            parts.append(f"格网 {grid['grid_id']} 的分析区域内相对风险为 {score.value} [{score.evidence_id}]。")
    return "".join(parts)


def _query_answer(result: ToolResult, evidence: list[EvidenceFact]) -> str:
    rows = result.data if isinstance(result.data, list) else []
    returned = next((item for item in evidence if item.metric == "query_result_count"), None)
    total = next((item for item in evidence if item.metric == "query_total_match_count"), None)
    parts: list[str] = []
    if total is not None and returned is not None:
        parts.append(f"共找到 {total.value} 个满足条件的格网 [{total.evidence_id}]，本次返回 {returned.value} 个 [{returned.evidence_id}]。")
    thresholds = [item for item in evidence if item.metric == "query_threshold"]
    if thresholds:
        parts.append("筛选阈值为" + "、".join(f"{item.label} {item.value} [{item.evidence_id}]" for item in thresholds) + "。")
    for row in rows[:3]:
        grid_id = row.get("grid_id")
        grid_fact = next((item for item in evidence if item.metric == "grid_result" and item.grid_id == grid_id), None)
        exposure = next((item for item in evidence if item.metric == "exposure_score" and item.grid_id == grid_id), None)
        green = next((item for item in evidence if item.metric == "green_fraction_land" and item.grid_id == grid_id), None)
        citations = " ".join(f"[{item.evidence_id}]" for item in (grid_fact, exposure, green) if item is not None)
        parts.append(
            f"格网 {grid_id}：暴露分数 {exposure.value if exposure else '无数据'}，"
            f"绿地比例 {green.value if green else '无数据'} {citations}。"
        )
    return "".join(parts) if parts else "未找到满足全部筛选条件的可分析陆地格网。"


def _contains_numeric_value(answer: str, expected: Any) -> bool:
    if not isinstance(expected, (int, float)):
        return str(expected) in answer
    scrubbed = re.sub(r"\[E\d+\]|M4B-[A-Z0-9-]+", " ", answer)
    for token in re.findall(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?", scrubbed):
        if abs(float(token) - float(expected)) <= max(0.005, abs(float(expected)) * 0.005):
            return True
    return False


def _explicit_grid_id(text: str) -> str | None:
    match = re.search(r"M4B-R-[A-Z0-9-]+", text, re.I)
    return match.group(0).upper() if match else None


def _normalize_action_arguments(
    arguments: dict[str, Any],
    action_grid_id: str | None,
) -> tuple[dict[str, Any], bool]:
    normalized = dict(arguments)
    scope = normalized.get("scope")
    if scope in {"selected_grid", "grid"} and not normalized.get("grid_id"):
        if not action_grid_id:
            raise ValueError("grid action request requires selected_grid_id or explicit grid_id")
        normalized["grid_id"] = action_grid_id
        return normalized, True
    return normalized, False


def _provider_data(tool_name: str, data: Any) -> Any:
    """Keep provider context compact while API responses retain full data."""
    if tool_name == "query_grids" and isinstance(data, list):
        fields = ("grid_id", "analysis_status", "risk_score", "population_total", "exposure_score", "green_fraction_land")
        return [{key: row.get(key) for key in fields} for row in data if isinstance(row, dict)]
    if tool_name == "compare_grids" and isinstance(data, dict):
        rows = data.get("grids", [])
        fields = ("grid_id", "risk_score", "population_total", "lst_median_c", "green_fraction_land")
        return {"grids": [{key: row.get(key) for key in fields} for row in rows if isinstance(row, dict)], "deltas": data.get("deltas", [])}
    return data


def _citation_instruction(result: ToolResult) -> str | None:
    """Give the provider an explicit metric-to-ID hint without changing facts."""
    if result.tool_name == "compare_grids":
        risk_delta = next((item for item in result.evidence if item.metric == "risk_delta"), None)
        if risk_delta is not None:
            return (
                "Citation contract for this comparison: if you state the risk difference "
                f"{risk_delta.value}, cite exactly [{risk_delta.evidence_id}]. Do not cite an individual risk-score fact for that delta. "
                "Do not mention a rank number, percentile, or bare 100 unless that same claim cites the exact supporting fact. "
                "The safest finalizer is one concise claim containing only the risk difference."
            )
    if result.tool_name == "query_grids":
        return (
            "Query finalizer contract: summarize the first three returned grids with exact exposure_score and "
            "green_fraction_land values, then state query_total_match_count. Do not number the list with digits "
            "or write ordinal digits such as 1, 2, or 3; those presentation numbers are not measurements."
        )
    return None


def _repair_focus(results: list[ToolResult]) -> str:
    if not results:
        return ""
    if results[-1].tool_name == "compare_grids":
        return (
            "For this comparison repair, return one concise claim containing only the exact risk_delta and its Evidence ID. "
            "Do not mention percentile, rank, 100, or any additional number. "
        )
    if results[-1].tool_name == "query_grids":
        return (
            "For this query repair, do not use numbered-list markers or ordinal digits. Name each grid directly, "
            "copy its exact exposure_score and green_fraction_land with their Evidence IDs, and cite query_total_match_count. "
        )
    return ""
