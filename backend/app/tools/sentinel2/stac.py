from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import planetary_computer
import pystac
import requests
from pystac_client import Client

from .assets import discover_asset_keys
from .cache import SentinelCache, stable_cache_key
from .metadata import ReflectanceScalingContract, parse_reflectance_scaling


class SentinelStacClient:
    def __init__(self, url: str, collection: str, cache: SentinelCache) -> None:
        self.url = url.rstrip("/")
        self.collection = collection
        self.cache = cache
        self.network_reads = 0
        self.cache_hits = 0

    def search(
        self,
        bbox: tuple[float, float, float, float],
        start: str,
        end: str,
    ) -> list[dict[str, Any]]:
        request = {
            "collection": self.collection,
            "bbox": bbox,
            "datetime": [start, end],
        }
        path = self.cache.search_path(stable_cache_key(request))
        cached = self.cache.read_json(path)
        if cached is not None:
            self.cache_hits += 1
            return list(cached["features"])
        items = Client.open(self.url).search(
            collections=[self.collection],
            bbox=bbox,
            datetime=f"{start}/{end}",
            max_items=500,
        ).item_collection()
        payload = {
            "type": "FeatureCollection",
            "request": request,
            "retrieved_at": datetime.now(UTC).isoformat(),
            "features": [item.to_dict() for item in items],
        }
        self.cache.write_json(path, payload)
        self.network_reads += 1
        return list(payload["features"])

    @staticmethod
    def signed_asset_href(item_dict: dict[str, Any], asset_key: str) -> str:
        item = pystac.Item.from_dict(item_dict)
        return planetary_computer.sign(item).assets[asset_key].href

    def product_metadata(
        self, item: dict[str, Any]
    ) -> tuple[ReflectanceScalingContract, str]:
        keys = discover_asset_keys(item)
        key = keys["product_metadata"]
        if key is None:
            raise ValueError("Sentinel STAC item lacks product metadata asset")
        path = self.cache.metadata_path(item["id"])
        if path.exists():
            self.cache_hits += 1
        else:
            href = self.signed_asset_href(item, key)
            response = requests.get(href, timeout=60)
            response.raise_for_status()
            self.cache.write_bytes(path, response.content)
            self.network_reads += 1
        return parse_reflectance_scaling(path.read_bytes()), str(path)

