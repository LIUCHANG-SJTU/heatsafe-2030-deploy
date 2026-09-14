from __future__ import annotations

import re
from typing import Any

from .evidence import EvidenceFact
from .schemas import AgentValidation, MapAction


_REF_RE = re.compile(r"\[E(\d+)\]")
_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?(?:°C)?(?![A-Za-z])")
_FORBIDDEN = re.compile(r"死亡概率|患病概率|mortality probability|health[- ]outcome probability|杭州市级|杭州全市|citywide absolute|增加\s*\d+%?.*风险|what if|counterfactual|scenario", re.I)
_UNSUPPORTED_ABSOLUTE_WORDING = re.compile(r"地表温度极端|人口密集|敏感人群比例较高|extreme heatwave|persistent extreme", re.I)


class AgentResponseValidator:
    def validate(self, answer: str, evidence: list[EvidenceFact], map_actions: list[MapAction] | None = None) -> AgentValidation:
        errors: list[str] = []
        by_id = {item.evidence_id: item for item in evidence if item.evidence_id}
        refs = [f"E{match}" for match in _REF_RE.findall(answer)]
        if not refs and _NUMBER_RE.search(answer):
            errors.append("quantitative answer must cite evidence")
        for ref in refs:
            if ref not in by_id:
                errors.append(f"unknown evidence reference: {ref}")
        disclaimer = any(marker in answer.lower() for marker in ["不代表", "不是", "not a", "does not", "not mortality", "not health", "不支持"])
        if _FORBIDDEN.search(answer) and not disclaimer:
            errors.append("forbidden scope or scenario claim")
        if _UNSUPPORTED_ABSOLUTE_WORDING.search(answer):
            errors.append("unsupported absolute wording; describe conditions relative to the analysis area")
        # Every quantitative token in a grounded answer must match a cited fact, allowing display rounding.
        cited_values = [by_id[ref].value for ref in refs if ref in by_id]
        for token_match in _NUMBER_RE.finditer(answer):
            token = token_match.group(0)
            normalized = token.replace(",", "").replace("%", "").replace("°C", "")
            try:
                value = float(normalized)
            except ValueError:
                continue
            # Fractions in the artifact may be rendered as percentages, e.g.
            # 1.0 -> 100%. Do not apply this conversion to a bare number.
            # Chinese claims may place the unit/percentile marker farther from
            # the number than an English word boundary. Keep this bounded to
            # the surrounding sentence so a separate claim cannot authorize it.
            sentence_start = max(answer.rfind("。", 0, token_match.start()), answer.rfind("，", 0, token_match.start()), answer.rfind(";", 0, token_match.start())) + 1
            sentence_end_candidates = [index for index in (answer.find("。", token_match.end()), answer.find("，", token_match.end()), answer.find(";", token_match.end())) if index >= 0]
            sentence_end = min(sentence_end_candidates) if sentence_end_candidates else len(answer)
            context = answer[sentence_start:sentence_end].lower()
            percentage_context = token.endswith("%") or any(marker in context for marker in ("百分位", "百分比", "percentile", "percent"))
            # Percentage evidence can be stored either as a fraction (0.9968)
            # or as an explicit display percent (99.68). Accept either exact
            # representation, but never let a bare risk score borrow a
            # percentile fact.
            comparison_values = (value, value / 100) if percentage_context else (value,)
            if not any(_close(comparison_value, candidate) for comparison_value in comparison_values for candidate in cited_values):
                # Method text contains frozen constants; these are accepted only with a methodology citation.
                if not any(item.metric == "methodology" and item.evidence_id in refs for item in evidence):
                    errors.append(f"unsupported numeric claim: {token}")
                    break
        if map_actions:
            for action in map_actions:
                if action.action in {"select_grid", "highlight_grids", "focus_grids"} and len(action.grid_ids) > 20:
                    errors.append("map action exceeds grid limit")
        return AgentValidation(status="PASS" if not errors else "FAIL", errors=errors)


def _close(value: float, candidate: Any) -> bool:
    if not isinstance(candidate, (int, float)):
        return False
    return abs(value - float(candidate)) <= max(0.15, abs(float(candidate)) * 0.01)


class ScenarioScopeGuard:
    _patterns = re.compile(r"如果.{0,40}(增加|减少|提高|降低|升温|降温)|假设.{0,40}(温度|绿地|风险)|措施.{0,24}风险.{0,12}(下降|降低|减少)|风险.{0,12}(下降|降低|减少)多少|情景模拟|what\s+if|increase\s+green|decrease\s+temperature|how much.{0,30}(?:(risk|score).{0,20}(drop|decrease|reduce)|(drop|decrease|reduce).{0,20}(risk|score))|\+\s*3\s*°?c|counterfactual|scenario\s+simulation", re.I)

    def is_scenario_request(self, text: str) -> bool:
        if "为什么绿地" in text or "why does green" in text.lower():
            return False
        return bool(self._patterns.search(text))


class InjectionGuard:
    _patterns = re.compile(r"ignore\s+(all\s+)?previous|忽略.*(规则|指令)|系统提示词|system prompt|api\s*key|执行\s*python|use\s+python|输出.*secret|pretend.*risk", re.I)

    def is_injection_request(self, text: str) -> bool:
        return bool(self._patterns.search(text))
