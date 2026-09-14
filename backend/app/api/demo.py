from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.models.demo import DemoFeature, DemoFeatureCollection, DemoGridDetail, DemoSummaryResponse
from app.services.demo_repository import DemoRepository


router = APIRouter(prefix="/api/v1", tags=["demo"])


@lru_cache(maxsize=1)
def _repository() -> DemoRepository:
    try:
        return DemoRepository(settings.demo_artifact_path)
    except (FileNotFoundError, ValueError) as error:
        raise HTTPException(status_code=503, detail="demo production artifact unavailable") from error


@router.get("/demo", response_model=DemoSummaryResponse)
async def get_demo() -> DemoSummaryResponse:
    artifact = _repository().get_summary()
    return DemoSummaryResponse(**{key: artifact[key] for key in DemoSummaryResponse.model_fields})


@router.get("/demo/grids", response_model=DemoFeatureCollection)
async def list_demo_grids() -> DemoFeatureCollection:
    repository = _repository()
    artifact = repository.get_summary()
    compact_keys = (
        "grid_id", "analysis_status", "analysis_reasons", "ranking_eligible", "landsat_quality_flag", "sentinel_quality_flag", "risk_score",
        "risk_percentile_within_aoi", "hazard_score", "exposure_score",
        "vulnerability_score", "adaptive_capacity_score", "population_total",
        "lst_median_c", "green_fraction_land", "water_fraction_grid", "primary_driver",
    )
    features = []
    for grid in repository.iter_grids():
        properties = {key: grid.get(key) for key in compact_keys}
        properties.update({"H": grid.get("hazard_score"), "E": grid.get("exposure_score"), "V": grid.get("vulnerability_score"), "A": grid.get("adaptive_capacity_score")})
        features.append(DemoFeature(id=grid["grid_id"], geometry=grid["geometry"], properties=properties))
    return DemoFeatureCollection(name=artifact["demo_id"], features=features)


@router.get("/demo/grids/{grid_id}", response_model=DemoGridDetail)
async def get_demo_grid(grid_id: str) -> DemoGridDetail:
    repository = _repository()
    artifact = repository.get_summary()
    try:
        grid = repository.get_grid(grid_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="demo grid not found")
    provenance = {
        "source_ids": grid.get("source_ids", []),
        "manifest": "data/provenance/demo_v1/manifest.json",
    }
    quality = {
        "lst_valid_fraction": grid.get("lst_valid_fraction"),
        "sentinel_valid_fraction": grid.get("sentinel_valid_fraction"),
        "analysis_status": grid.get("analysis_status"),
    }
    return DemoGridDetail(**grid, methods=artifact["methods"], quality=quality, provenance=provenance, temporal_context=artifact.get("temporal_context"))
