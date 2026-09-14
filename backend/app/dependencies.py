from functools import lru_cache

from app.action.service import ActionRecommendationService
from app.agent.orchestrator import HeatSafeOrchestrator
from app.config import settings
from app.agent.config import agent_settings
from app.agent.orchestrator_v1 import GroundedAgent
from app.agent.providers.openai_compatible import OpenAICompatibleProvider
from app.agent.query_service import HeatSafeQueryService
from app.services.demo_repository import DemoRepository


@lru_cache
def _get_orchestrator() -> HeatSafeOrchestrator:
    return HeatSafeOrchestrator(
        fixture_grid_path=settings.fixture_grid_path,
        provenance_path=settings.provenance_path,
        worldpop_artifact_path=settings.worldpop_artifact_path,
        landsat_artifact_path=settings.landsat_artifact_path,
        sentinel_artifact_path=settings.sentinel_artifact_path,
        era5_temporal_context_path=settings.era5_temporal_context_path,
        hazard_artifact_path=settings.hazard_artifact_path,
    )


async def get_orchestrator() -> HeatSafeOrchestrator:
    return _get_orchestrator()


@lru_cache(maxsize=1)
def _get_demo_query_service() -> HeatSafeQueryService:
    return HeatSafeQueryService(DemoRepository(settings.demo_artifact_path))


@lru_cache(maxsize=1)
def _get_grounded_agent() -> GroundedAgent:
    provider = None
    if agent_settings.configured and agent_settings.provider == "openai_compatible":
        provider = OpenAICompatibleProvider(
            agent_settings.base_url,
            agent_settings.api_key,
            agent_settings.model,
            agent_settings.timeout_seconds,
            agent_settings.max_output_tokens,
            agent_settings.thinking_mode,
        )
    return GroundedAgent(_get_demo_query_service(), provider=provider)


async def get_grounded_agent() -> GroundedAgent:
    return _get_grounded_agent()


@lru_cache(maxsize=1)
def _get_action_recommendation_service() -> ActionRecommendationService:
    return ActionRecommendationService(_get_demo_query_service())


async def get_action_recommendation_service() -> ActionRecommendationService:
    return _get_action_recommendation_service()
