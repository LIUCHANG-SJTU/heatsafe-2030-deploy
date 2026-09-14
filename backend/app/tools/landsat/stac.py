from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import planetary_computer
import pystac
from pystac_client import Client

from app.models.landsat import SceneCandidate

from .cache import LandsatCache, stable_cache_key


def discover_asset_keys(item: dict[str, Any]) -> dict[str, str | None]:
    assets = item.get("assets", {})
    st_key = None
    qa_key = None
    st_qa_key = None
    for key, asset in assets.items():
        title = str(asset.get("title", "")).lower()
        description = str(asset.get("description", "")).lower()
        roles = {str(role).lower() for role in asset.get("roles", [])}
        if "surface temperature band" in title or (
            "surface temperature" in description and "temperature" in roles
        ):
            st_key = key
        if "pixel quality assessment band" in title or "qa_pixel" in description:
            qa_key = key
        if "surface temperature quality assessment band" in title:
            st_qa_key = key
    return {"st": st_key, "qa_pixel": qa_key, "st_qa": st_qa_key}


def asset_band_metadata(item: dict[str, Any], asset_key: str) -> dict[str, Any]:
    asset = item["assets"][asset_key]
    bands = asset.get("raster:bands", [])
    return dict(bands[0]) if bands else {}


def product_id_from_asset(item: dict[str, Any], st_asset_key: str | None) -> str:
    if not st_asset_key:
        return item["id"]
    filename = Path(urlparse(item["assets"][st_asset_key]["href"]).path).name
    suffix = "_ST_B10.TIF"
    return filename[: -len(suffix)] if filename.endswith(suffix) else item["id"]


def candidate_from_item(item: dict[str, Any]) -> SceneCandidate:
    keys = discover_asset_keys(item)
    properties = item["properties"]
    return SceneCandidate(
        scene_id=item["id"],
        product_id=product_id_from_asset(item, keys["st"]),
        platform=properties.get("platform", "unknown"),
        acquisition_datetime=properties["datetime"],
        scene_cloud_cover=float(properties.get("eo:cloud_cover", 100)),
        st_asset_available=keys["st"] is not None,
        qa_asset_available=keys["qa_pixel"] is not None,
        st_asset_key=keys["st"],
        qa_asset_key=keys["qa_pixel"],
        st_qa_asset_key=keys["st_qa"],
    )


class LandsatStacClient:
    def __init__(self, url: str, collection: str, cache: LandsatCache) -> None:
        self.url = url
        self.collection = collection
        self.cache = cache
        self.network_reads = 0
        self.cache_hits = 0

    def search(
        self,
        bbox: tuple[float, float, float, float],
        start: str,
        end: str,
        max_cloud_cover: float,
    ) -> list[dict[str, Any]]:
        request = {
            "collection": self.collection,
            "bbox": bbox,
            "datetime": [start, end],
            "eo:cloud_cover_lte": max_cloud_cover,
            "platforms": ["landsat-8", "landsat-9"],
        }
        cache_key = f"search-{stable_cache_key(request)}.json"
        path = self.cache.json_path(cache_key)
        cached = self.cache.read_json(path)
        if cached is not None:
            self.cache_hits += 1
            return list(cached["features"])
        catalog = Client.open(self.url)
        items = catalog.search(
            collections=[self.collection],
            bbox=bbox,
            datetime=f"{start}/{end}",
            query={"eo:cloud_cover": {"lte": max_cloud_cover}},
            max_items=200,
        ).item_collection()
        features = [
            item.to_dict()
            for item in items
            if item.properties.get("platform") in {"landsat-8", "landsat-9"}
        ]
        payload = {
            "type": "FeatureCollection",
            "request": request,
            "features": features,
        }
        self.cache.write_json(path, payload)
        self.network_reads += 1
        return list(payload["features"])

    @staticmethod
    def signed_asset_href(item_dict: dict[str, Any], asset_key: str) -> str:
        item = pystac.Item.from_dict(item_dict)
        signed = planetary_computer.sign(item)
        return signed.assets[asset_key].href
