from __future__ import annotations

import numpy as np


QA_BITS = {
    "fill": 0,
    "dilated_cloud": 1,
    "cirrus": 2,
    "cloud": 3,
    "cloud_shadow": 4,
    "snow": 5,
    "clear": 6,
    "water": 7,
}
EXCLUDED_BITS = (0, 1, 2, 3, 4, 5)


def qa_bit(qa: np.ndarray, bit: int) -> np.ndarray:
    values = np.asarray(qa, dtype=np.uint16)
    return ((values >> bit) & 1).astype(bool)


def decode_qa_pixel(qa: np.ndarray) -> dict[str, np.ndarray]:
    return {name: qa_bit(qa, bit) for name, bit in QA_BITS.items()}


def valid_qa_mask(qa: np.ndarray) -> np.ndarray:
    """Mask fill/cloud/cirrus/shadow/snow while intentionally retaining water."""
    values = np.asarray(qa, dtype=np.uint16)
    invalid = np.zeros(values.shape, dtype=bool)
    for bit in EXCLUDED_BITS:
        invalid |= qa_bit(values, bit)
    return ~invalid


def cloud_qa_mask(qa: np.ndarray) -> np.ndarray:
    """Cloud-related QA only: dilated cloud, cirrus, cloud, and shadow."""
    values = np.asarray(qa, dtype=np.uint16)
    cloud = np.zeros(values.shape, dtype=bool)
    for bit in (1, 2, 3, 4):
        cloud |= qa_bit(values, bit)
    return cloud
