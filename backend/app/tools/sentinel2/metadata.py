from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass


def _local_name(tag: str) -> str:
    return tag.split("}")[-1]


def _normalize_band_name(name: str) -> str:
    prefix = name[0].upper()
    number = name[1:].lstrip("0")
    return prefix + (number or "0")


@dataclass(frozen=True)
class ReflectanceScalingContract:
    quantification_value: float
    scale: float
    b04_add_offset_dn: float
    b08_add_offset_dn: float
    b04_offset: float
    b08_offset: float
    nodata: int
    saturated: int
    source: str = "Sentinel-2 L2A product metadata MTD_MSIL2A.xml"


def parse_reflectance_scaling(xml_bytes: bytes) -> ReflectanceScalingContract:
    root = ET.fromstring(xml_bytes)
    quantification = None
    band_ids: dict[str, str] = {}
    offsets: dict[str, float] = {}
    special_values: dict[str, int] = {}
    pending_special: str | None = None
    for element in root.iter():
        name = _local_name(element.tag)
        text = (element.text or "").strip()
        if name == "BOA_QUANTIFICATION_VALUE":
            quantification = float(text)
        elif name == "Spectral_Information":
            band_ids[_normalize_band_name(element.attrib["physicalBand"])] = element.attrib["bandId"]
        elif name == "BOA_ADD_OFFSET":
            offsets[element.attrib["band_id"]] = float(text)
        elif name == "SPECIAL_VALUE_TEXT":
            pending_special = text.upper()
        elif name == "SPECIAL_VALUE_INDEX" and pending_special:
            special_values[pending_special] = int(text)
            pending_special = None
    if quantification is None or quantification <= 0:
        raise ValueError("product metadata lacks valid BOA_QUANTIFICATION_VALUE")
    for required in ("B4", "B8"):
        if required not in band_ids or band_ids[required] not in offsets:
            raise ValueError(f"product metadata lacks BOA offset for {required}")
    if "NODATA" not in special_values or "SATURATED" not in special_values:
        raise ValueError("product metadata lacks nodata/saturated special values")
    b04_add = offsets[band_ids["B4"]]
    b08_add = offsets[band_ids["B8"]]
    return ReflectanceScalingContract(
        quantification_value=quantification,
        scale=1.0 / quantification,
        b04_add_offset_dn=b04_add,
        b08_add_offset_dn=b08_add,
        b04_offset=b04_add / quantification,
        b08_offset=b08_add / quantification,
        nodata=special_values["NODATA"],
        saturated=special_values["SATURATED"],
    )

