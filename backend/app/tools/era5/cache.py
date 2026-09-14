from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def request_hash(dataset_id: str, request: dict[str, Any]) -> str:
    payload = {"dataset_id": dataset_id, "request": request}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def file_checksum(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


class ERA5Cache:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.requests = root / "requests"
        self.responses = root / "responses"
        self.baseline = root / "baseline"
        self.event = root / "event"
        self.manifests = root / "manifests"
        for directory in (
            self.requests,
            self.responses,
            self.baseline,
            self.event,
            self.manifests,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def request_path(self, key: str) -> Path:
        return self.requests / f"{key}.json"

    def response_path(self, key: str, label: str) -> Path:
        return self.responses / f"{label}-{key}.nc"

    @staticmethod
    def write_json(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
