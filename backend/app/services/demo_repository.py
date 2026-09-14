from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator


class DemoRepository:
    """Read-only access to the frozen M4C1 demo artifact."""

    def __init__(self, artifact_path: Path, geojson_path: Path | None = None) -> None:
        self.artifact_path = artifact_path
        self.geojson_path = geojson_path or artifact_path.with_suffix(".geojson")
        if not artifact_path.exists():
            raise FileNotFoundError(artifact_path)
        self._artifact_sha256 = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        self._geojson_sha256 = (
            hashlib.sha256(self.geojson_path.read_bytes()).hexdigest()
            if self.geojson_path.exists()
            else None
        )
        self._artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        if not isinstance(self._artifact, dict) or not isinstance(self._artifact.get("grids"), list):
            raise ValueError("invalid demo artifact")
        self._by_grid = {str(grid["grid_id"]): grid for grid in self._artifact["grids"]}

    @property
    def artifact_sha256(self) -> str:
        return self._artifact_sha256

    @property
    def geojson_sha256(self) -> str | None:
        return self._geojson_sha256

    def get_summary(self) -> dict[str, Any]:
        return {key: self._artifact[key] for key in self._artifact if key != "grids"}

    def get_grid(self, grid_id: str) -> dict[str, Any]:
        try:
            return self._by_grid[grid_id]
        except KeyError as error:
            raise KeyError(f"unknown grid_id: {grid_id}") from error

    def has_grid(self, grid_id: str) -> bool:
        return grid_id in self._by_grid

    def iter_grids(self) -> Iterator[dict[str, Any]]:
        return iter(self._artifact["grids"])

    def get_grid_collection(self) -> list[dict[str, Any]]:
        return list(self._artifact["grids"])

    def get_hotspots(self, limit: int = 10) -> list[dict[str, Any]]:
        return list(self._artifact["summary"].get("top_10_hotspots", []))[:limit]


@lru_cache(maxsize=1)
def get_demo_repository(artifact_path: str) -> DemoRepository:
    path = Path(artifact_path)
    return DemoRepository(path)
