from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_cache_key(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def file_checksum(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


class LandsatCache:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.stac = root / "stac"
        self.windows = root / "windows"
        self.manifests = root / "manifests"
        for directory in (self.stac, self.windows, self.manifests):
            directory.mkdir(parents=True, exist_ok=True)

    def json_path(self, name: str) -> Path:
        return self.stac / name

    def window_path(self, scene_id: str, asset_key: str) -> Path:
        return self.windows / f"{scene_id}.{asset_key}.tif"

    @staticmethod
    def write_json(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)

    @staticmethod
    def read_json(path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

