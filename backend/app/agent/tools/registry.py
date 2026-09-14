from __future__ import annotations

from typing import Any, Callable

from app.action.service import ActionRecommendationService

from ..query_service import HeatSafeQueryService
from ..semantic_contract import QueryFieldCanonicalizer
from ..schemas import CompareGridsInput, QueryGridsInput
from .contracts import EmptyInput, GridInput, HotspotsInput, MethodologyInput, RecommendActionsInput, tool_names


class ToolRegistry:
    def __init__(self, service: HeatSafeQueryService) -> None:
        self.service = service
        self.action_service = ActionRecommendationService(service)
        self.query_field_canonicalizer = QueryFieldCanonicalizer()
        self._handlers: dict[str, Callable[[Any], Any]] = {
            "get_demo_summary": lambda _: service.summary(),
            "inspect_grid": lambda request: service.inspect(request.grid_id),
            "list_hotspots": lambda request: service.hotspots(request.limit),
            "compare_grids": service.compare,
            "query_grids": service.query,
            "explain_risk": lambda request: service.explain(request.grid_id),
            "get_methodology": lambda request: service.methodology(request.topic),
            "recommend_actions": self._recommend_actions,
        }
        self._models: dict[str, type[Any]] = {
            "get_demo_summary": EmptyInput,
            "inspect_grid": GridInput,
            "list_hotspots": HotspotsInput,
            "compare_grids": CompareGridsInput,
            "query_grids": QueryGridsInput,
            "explain_risk": GridInput,
            "recommend_actions": RecommendActionsInput,
        }

    @property
    def names(self) -> list[str]:
        return tool_names()

    def execute(self, name: str, payload: dict[str, Any] | Any):
        if name not in self._handlers:
            raise ValueError(f"unknown public tool: {name}")
        if name == "query_grids" and isinstance(payload, dict):
            payload, _ = self.query_field_canonicalizer.canonicalize(payload)
        if name == "get_methodology":
            request = payload if hasattr(payload, "topic") else MethodologyInput.model_validate(payload)
        else:
            model = self._models[name]
            request = payload if isinstance(payload, model) else model.model_validate(payload)
        return self._handlers[name](request)

    def _recommend_actions(self, request: RecommendActionsInput):
        if request.scope == "hotspots":
            return self.action_service.recommend_for_hotspots(request.limit)
        if request.grid_id is None:
            raise ValueError("grid action scope requires grid_id")
        return self.action_service.recommend_for_grid(request.grid_id, limit=request.limit)
