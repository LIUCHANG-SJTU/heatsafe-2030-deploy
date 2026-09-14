from __future__ import annotations

import numpy as np

from app.tools.era5.percentile import average_rank_01


def spatial_heat_scores(lst_median_c: np.ndarray) -> np.ndarray:
    return average_rank_01(np.asarray(lst_median_c, dtype=float))
