from fastapi import FastAPI

from app import __version__
from app.api.analysis import router as analysis_router
from app.api.demo import router as demo_router
from app.api.scenario import router as scenario_router
from app.api.agent import router as agent_router
from app.api.actions import router as actions_router
from app.config import settings


app = FastAPI(
    title="HeatSafe 2030 API",
    version=__version__,
    description=(
        "Deterministic urban heat risk API with explicitly selectable WorldPop "
        "and Landsat artifacts. Mixed outputs are not a complete real analysis "
        "of Hangzhou."
    ),
)
app.include_router(analysis_router)
app.include_router(demo_router)
app.include_router(scenario_router)
app.include_router(agent_router)
app.include_router(actions_router)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "service": "heatsafe-2030",
        "version": __version__,
        "data_mode": settings.data_mode,
        "default_analysis_mode": settings.data_mode,
        "real_worldpop_artifact_available": settings.worldpop_artifact_path.exists(),
        "real_worldpop_artifact_mode": (
            "REAL" if settings.worldpop_artifact_path.exists() else "N/A"
        ),
        "real_landsat_artifact_available": settings.landsat_artifact_path.exists(),
        "real_landsat_artifact_mode": (
            "REAL" if settings.landsat_artifact_path.exists() else "N/A"
        ),
        "real_sentinel_artifact_available": settings.sentinel_artifact_path.exists(),
        "real_sentinel_artifact_mode": (
            "REAL" if settings.sentinel_artifact_path.exists() else "N/A"
        ),
        "real_era5_temporal_context_available": settings.era5_temporal_context_path.exists(),
        "real_hazard_artifact_available": settings.hazard_artifact_path.exists(),
        "full_analysis_mode_with_real_artifacts": (
            "REAL"
            if all(
                path.exists()
                for path in (
                    settings.worldpop_artifact_path,
                    settings.landsat_artifact_path,
                    settings.sentinel_artifact_path,
                    settings.era5_temporal_context_path,
                    settings.hazard_artifact_path,
                )
            )
            else "MIXED"
        ),
    }
