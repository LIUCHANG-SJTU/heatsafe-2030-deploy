from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.agent.orchestrator import HeatSafeOrchestrator
from app.dependencies import get_orchestrator
from app.models.api import AnalysisRequest, AnalysisResponse
from app.models.grid import GridCell, GridCollection


router = APIRouter(prefix="/api/v1", tags=["analysis"])


@router.get("/grids", response_model=GridCollection)
async def list_grids(
    limit: int = Query(default=100, ge=1, le=100),
    population_mode: Literal["fixture", "real"] = "fixture",
    temperature_mode: Literal["fixture", "real"] = "fixture",
    vegetation_mode: Literal["fixture", "real"] = "fixture",
    temporal_mode: Literal["fixture", "real"] = "fixture",
    orchestrator: HeatSafeOrchestrator = Depends(get_orchestrator),
) -> GridCollection:
    try:
        cells = orchestrator.baseline_grids(
            population_mode, temperature_mode, vegetation_mode, temporal_mode
        )[:limit]
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    mode = cells[0].data_mode if cells else "FIXTURE"
    return GridCollection(data_mode=mode, cells=cells)


@router.get("/grids/{grid_id}", response_model=GridCell)
async def get_grid(
    grid_id: str,
    population_mode: Literal["fixture", "real"] = "fixture",
    temperature_mode: Literal["fixture", "real"] = "fixture",
    vegetation_mode: Literal["fixture", "real"] = "fixture",
    temporal_mode: Literal["fixture", "real"] = "fixture",
    orchestrator: HeatSafeOrchestrator = Depends(get_orchestrator),
) -> GridCell:
    try:
        cells = orchestrator.baseline_grids(
            population_mode, temperature_mode, vegetation_mode, temporal_mode
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    for cell in cells:
        if cell.grid_id == grid_id:
            return cell
    raise HTTPException(status_code=404, detail="grid not found")


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze(
    request: AnalysisRequest,
    orchestrator: HeatSafeOrchestrator = Depends(get_orchestrator),
) -> AnalysisResponse:
    try:
        return orchestrator.analyze(request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
