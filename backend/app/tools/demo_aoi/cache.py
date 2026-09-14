from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable


PROCESSING_CONTRACT = "M4B_SATELLITE_V1"


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_key(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def checksum(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


class M4BSatelliteCache:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.windows = root / "windows"
        self.manifests = root / "manifests"
        self.windows.mkdir(parents=True, exist_ok=True)
        self.manifests.mkdir(parents=True, exist_ok=True)
        self.network_reads = {"landsat": 0, "sentinel": 0}
        self.cache_hits = {"landsat": 0, "sentinel": 0}

    def window_path(
        self,
        provider: str,
        scene_id: str,
        asset_key: str,
        bounds_projected: tuple[float, float, float, float],
    ) -> Path:
        contract = {
            "provider": provider,
            "scene_id": scene_id,
            "asset_key": asset_key,
            "bounds_projected": list(bounds_projected),
            "processing_contract": PROCESSING_CONTRACT,
        }
        return self.windows / f"{provider}-{stable_key(contract)}.tif"

    def ensure_window(
        self,
        provider: str,
        scene_id: str,
        asset_key: str,
        bounds_projected: tuple[float, float, float, float],
        create: Callable[[Path], None],
    ) -> Path:
        path = self.window_path(provider, scene_id, asset_key, bounds_projected)
        if path.exists() and path.stat().st_size > 0:
            self.cache_hits[provider] += 1
            return path
        create(path)
        if not path.exists() or path.stat().st_size == 0:
            raise RuntimeError("satellite window acquisition produced no artifact")
        self.network_reads[provider] += 1
        return path

    @staticmethod
    def write_json(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
