from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from .models import WorldPopQuery


class RequestBudgetExceeded(RuntimeError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def request_hash(query: WorldPopQuery) -> str:
    return hashlib.sha256(
        canonical_json(
            {"endpoint": query.endpoint.value, "payload": query.api_payload()}
        ).encode("utf-8")
    ).hexdigest()


class WorldPopCache:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.requests = root / "requests"
        self.responses = root / "responses"
        self.tasks = root / "tasks"
        self.manifests = root / "manifests"
        for directory in (self.requests, self.responses, self.tasks, self.manifests):
            directory.mkdir(parents=True, exist_ok=True)

    def request_path(self, key: str) -> Path:
        return self.requests / f"{key}.json"

    def task_path(self, key: str) -> Path:
        return self.tasks / f"{key}.json"

    def response_path(self, key: str) -> Path:
        return self.responses / f"{key}.json"

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


class RequestBudget:
    def __init__(self, path: Path, maximum: int) -> None:
        self.path = path
        self.maximum = maximum
        payload = WorldPopCache.read_json(path) or {}
        today = date.today().isoformat()
        if payload.get("date") == today:
            self.count = int(payload.get("count", 0))
        else:
            self.count = 0
        self._persist()

    @property
    def remaining(self) -> int:
        return max(0, self.maximum - self.count)

    def consume(self) -> None:
        if self.count >= self.maximum:
            raise RequestBudgetExceeded(
                f"WorldPop request budget exhausted ({self.count}/{self.maximum})"
            )
        self.count += 1
        self._persist()

    def _persist(self) -> None:
        WorldPopCache.write_json(
            self.path,
            {
                "date": date.today().isoformat(),
                "count": self.count,
                "maximum": self.maximum,
                "updated_at": datetime.now(UTC).isoformat(),
            },
        )

