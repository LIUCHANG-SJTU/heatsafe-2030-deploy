from fastapi import APIRouter, Depends, HTTPException

from app.agent.orchestrator import HeatSafeOrchestrator
from app.dependencies import get_orchestrator
from app.models.api import (
    AnalysisRequest,
    AnalysisResponse,
    ScenarioRequest,
)


router = APIRouter(prefix="/api/v1", tags=["scenario"])


@router.post("/scenario", response_model=AnalysisResponse)
async def scenario(
    request: ScenarioRequest,
    orchestrator: HeatSafeOrchestrator = Depends(get_orchestrator),
) -> AnalysisResponse:
    try:
        return orchestrator.analyze(
            AnalysisRequest(
                bbox=request.bbox,
                scenario_temperature_delta=request.temperature_delta,
                population_mode=request.population_mode,
                temperature_mode=request.temperature_mode,
                vegetation_mode=request.vegetation_mode,
                temporal_mode=request.temporal_mode,
            )
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
