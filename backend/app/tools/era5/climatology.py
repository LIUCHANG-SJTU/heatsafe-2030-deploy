from __future__ import annotations

import numpy as np
import pandas as pd


QUANTILE_METHOD = "linear"


def month_same_hour(series: pd.Series, month: int, utc_hour: int) -> pd.Series:
    if not isinstance(series.index, pd.DatetimeIndex):
        raise TypeError("series requires a DatetimeIndex")
    if month not in range(1, 13) or utc_hour not in range(24):
        raise ValueError("month and UTC hour are out of range")
    return series[
        (series.index.month == month) & (series.index.hour == utc_hour)
    ].dropna()


def july_same_hour(series: pd.Series, utc_hour: int) -> pd.Series:
    return month_same_hour(series, 7, utc_hour)


def month_hour_p90(
    series: pd.Series, months: tuple[int, ...] = (6, 7, 8)
) -> dict[tuple[int, int], dict[str, float | int | str]]:
    thresholds: dict[tuple[int, int], dict[str, float | int | str]] = {}
    for month in months:
        for hour in range(24):
            values = month_same_hour(series, month, hour).to_numpy(dtype=float)
            if not values.size:
                raise ValueError(
                    f"baseline has no samples for month {month}, UTC hour {hour}"
                )
            thresholds[(month, hour)] = {
                "temperature_p90_c": float(
                    np.quantile(values, 0.90, method=QUANTILE_METHOD)
                ),
                "sample_count": int(values.size),
                "quantile_method": QUANTILE_METHOD,
            }
    return thresholds


def hourly_july_p90(series: pd.Series) -> dict[int, dict[str, float | int | str]]:
    return {
        hour: metadata
        for (month, hour), metadata in month_hour_p90(series, (7,)).items()
    }


def month_hour_statistics(
    series: pd.Series, month: int, utc_hour: int
) -> dict[str, float | int]:
    values = month_same_hour(series, month, utc_hour).to_numpy(dtype=float)
    if not values.size:
        raise ValueError("same-month same-hour baseline is empty")
    return {
        "historical_mean_c": float(np.mean(values)),
        "historical_median_c": float(np.median(values)),
        "historical_p90_c": float(
            np.quantile(values, 0.90, method=QUANTILE_METHOD)
        ),
        "historical_p95_c": float(
            np.quantile(values, 0.95, method=QUANTILE_METHOD)
        ),
        "historical_std_c": float(np.std(values)),
        "baseline_sample_count": int(values.size),
    }


def baseline_statistics(series: pd.Series, utc_hour: int) -> dict[str, float | int]:
    return month_hour_statistics(series, 7, utc_hour)
