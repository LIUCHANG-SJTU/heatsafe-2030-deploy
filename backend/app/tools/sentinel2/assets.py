from __future__ import annotations

from typing import Any


def discover_asset_keys(item: dict[str, Any]) -> dict[str, str | None]:
    keys: dict[str, str | None] = {
        "b04": None,
        "b08": None,
        "scl": None,
        "product_metadata": None,
    }
    scores = {"b04": -1, "b08": -1}
    for key, asset in item.get("assets", {}).items():
        title = str(asset.get("title", "")).lower()
        bands = asset.get("eo:bands", [])
        band_names = {str(band.get("name", "")).upper() for band in bands}
        common_names = {str(band.get("common_name", "")).lower() for band in bands}
        b04_score = 4 if key.upper() == "B04" else 3 if "B04" in band_names else 1 if "red" in common_names else -1
        b08_score = 4 if key.upper() == "B08" else 3 if "B08" in band_names else 1 if "nir" in common_names else -1
        if b04_score > scores["b04"]:
            keys["b04"] = key
            scores["b04"] = b04_score
        if b08_score > scores["b08"]:
            keys["b08"] = key
            scores["b08"] = b08_score
        if "scene class" in title or key.upper() == "SCL":
            keys["scl"] = key
        if "product metadata" in title or key == "product-metadata":
            keys["product_metadata"] = key
    return keys


def projection_metadata(item: dict[str, Any], asset_key: str) -> dict[str, Any]:
    asset = item["assets"][asset_key]
    return {
        "epsg": asset.get(
            "proj:epsg",
            asset.get(
                "proj:code",
                item.get("properties", {}).get(
                    "proj:epsg", item.get("properties", {}).get("proj:code")
                ),
            ),
        ),
        "shape": asset.get("proj:shape"),
        "transform": asset.get("proj:transform"),
        "gsd": asset.get("gsd"),
        "raster_bands": asset.get("raster:bands"),
        "nodata": (
            asset.get("raster:bands", [{}])[0].get("nodata")
            if asset.get("raster:bands")
            else None
        ),
        "scale": (
            asset.get("raster:bands", [{}])[0].get("scale")
            if asset.get("raster:bands")
            else None
        ),
        "offset": (
            asset.get("raster:bands", [{}])[0].get("offset")
            if asset.get("raster:bands")
            else None
        ),
    }
