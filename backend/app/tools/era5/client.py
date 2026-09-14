from __future__ import annotations

from pathlib import Path
from typing import Any

import cdsapi

from .cache import ERA5Cache, request_hash


class ERA5CDSClient:
    def __init__(self, dataset_id: str, cache: ERA5Cache) -> None:
        self.dataset_id = dataset_id
        self.cache = cache
        self.network_reads = 0
        self.cache_hits = 0

    def retrieve(self, request: dict[str, Any], label: str) -> tuple[Path, str]:
        key = request_hash(self.dataset_id, request)
        target = self.cache.response_path(key, label)
        self.cache.write_json(
            self.cache.request_path(key),
            {"dataset_id": self.dataset_id, "request": request, "request_hash": key},
        )
        if target.exists() and target.stat().st_size > 0:
            self.cache_hits += 1
            return target, key
        temporary = target.with_suffix(".nc.part")
        client = cdsapi.Client(
            quiet=True,
            progress=False,
            retry_max=2,
            sleep_max=5,
            timeout=60,
        )
        client.retrieve(self.dataset_id, request, str(temporary))
        if not temporary.exists() or temporary.stat().st_size == 0:
            raise RuntimeError("CDS retrieval completed without a non-empty artifact")
        temporary.replace(target)
        self.network_reads += 1
        return target, key
