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


class SentinelCache:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.stac = root / "stac"
        self.metadata = root / "metadata"
        self.windows = root / "windows"
        self.manifests = root / "manifests"
        for directory in (self.stac, self.metadata, self.windows, self.manifests):
            directory.mkdir(parents=True, exist_ok=True)

    def search_path(self, key: str) -> Path:
        return self.stac / f"search-{key}.json"

    def item_path(self, scene_id: str) -> Path:
        return self.stac / f"{scene_id}.item.json"

    def metadata_path(self, scene_id: str) -> Path:
        return self.metadata / f"{scene_id}.product.xml"

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

    @staticmethod
    def write_bytes(path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(payload)
        temporary.replace(path)

