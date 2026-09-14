from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    data_mode: str = os.getenv("DATA_MODE", "FIXTURE")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "")
    fixture_grid_path: Path = Path(
        os.getenv("FIXTURE_GRID_PATH", PROJECT_DIR / "data/processed/fixture_grids.json")
    )
    provenance_path: Path = Path(
        os.getenv(
            "PROVENANCE_PATH",
            PROJECT_DIR / "data/provenance/fixture_grids.metadata.json",
        )
    )
    worldpop_api_url: str = os.getenv(
        "WORLDPOP_API_URL", "https://api.worldpop.org/v2"
    )
    worldpop_api_key: str = os.getenv("WORLDPOP_API_KEY", "")
    worldpop_max_concurrency: int = int(os.getenv("WORLDPOP_MAX_CONCURRENCY", "1"))
    worldpop_request_budget: int = int(os.getenv("WORLDPOP_REQUEST_BUDGET", "900"))
    worldpop_poll_initial_seconds: float = float(
        os.getenv("WORLDPOP_POLL_INITIAL_SECONDS", "2")
    )
    worldpop_poll_max_seconds: float = float(
        os.getenv("WORLDPOP_POLL_MAX_SECONDS", "16")
    )
    worldpop_task_timeout_seconds: float = float(
        os.getenv("WORLDPOP_TASK_TIMEOUT_SECONDS", "180")
    )
    worldpop_artifact_path: Path = Path(
        os.getenv(
            "WORLDPOP_ARTIFACT_PATH",
            PROJECT_DIR / "data/processed/worldpop/worldpop_population_2026.json",
        )
    )
    landsat_stac_url: str = os.getenv(
        "LANDSAT_STAC_URL", "https://planetarycomputer.microsoft.com/api/stac/v1"
    )
    landsat_collection: str = os.getenv("LANDSAT_COLLECTION", "landsat-c2-l2")
    landsat_search_start: str = os.getenv("LANDSAT_SEARCH_START", "2026-06-01")
    landsat_search_end: str = os.getenv("LANDSAT_SEARCH_END", "2026-08-25")
    landsat_max_scene_cloud_cover: float = float(
        os.getenv("LANDSAT_MAX_SCENE_CLOUD_COVER", "50")
    )
    landsat_artifact_path: Path = Path(
        os.getenv(
            "LANDSAT_ARTIFACT_PATH",
            PROJECT_DIR / "data/processed/landsat/landsat_lst_pilot_2026.json",
        )
    )
    sentinel_stac_url: str = os.getenv(
        "SENTINEL_STAC_URL", "https://planetarycomputer.microsoft.com/api/stac/v1"
    )
    sentinel_collection: str = os.getenv(
        "SENTINEL_COLLECTION", "sentinel-2-l2a"
    )
    sentinel_artifact_path: Path = Path(
        os.getenv(
            "SENTINEL_ARTIFACT_PATH",
            PROJECT_DIR
            / "data/processed/sentinel2/sentinel2_vegetation_pilot_2026.json",
        )
    )
    era5_temporal_context_path: Path = Path(
        os.getenv(
            "ERA5_TEMPORAL_CONTEXT_PATH",
            PROJECT_DIR / "data/processed/era5/era5_temporal_context.json",
        )
    )
    hazard_artifact_path: Path = Path(
        os.getenv(
            "HAZARD_ARTIFACT_PATH",
            PROJECT_DIR
            / "data/processed/hazard/spatiotemporal_hazard_pilot_2026.json",
        )
    )
    demo_artifact_path: Path = Path(
        os.getenv(
            "DEMO_ARTIFACT_PATH",
            PROJECT_DIR / "data/processed/analysis/heatsafe_demo_v1_2026.json",
        )
    )

    def __post_init__(self) -> None:
        if self.data_mode not in {"FIXTURE", "MIXED", "REAL"}:
            raise ValueError("DATA_MODE must be FIXTURE, MIXED, or REAL")
        if self.worldpop_max_concurrency not in {1, 2}:
            raise ValueError("WORLDPOP_MAX_CONCURRENCY must be 1 or 2 for M1")
        if self.worldpop_request_budget <= 0:
            raise ValueError("WORLDPOP_REQUEST_BUDGET must be positive")


settings = Settings()
