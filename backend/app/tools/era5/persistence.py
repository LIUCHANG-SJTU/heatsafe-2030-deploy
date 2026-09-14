from __future__ import annotations

import pandas as pd


def evaluate_persistence(
    temperatures: pd.Series,
    reference_time: pd.Timestamp,
    hourly_thresholds: dict[int, float],
) -> dict[str, int | bool]:
    expected = pd.date_range(end=reference_time, periods=72, freq="h")
    window = temperatures.reindex(expected)
    complete = bool(window.notna().all())
    if not complete:
        return {"event_window_complete": False}
    hot = pd.Series(
        [value > hourly_thresholds[timestamp.hour] for timestamp, value in window.items()],
        index=expected,
        dtype=bool,
    )
    current_run = 0
    max_run = 0
    for is_hot in hot:
        current_run = current_run + 1 if is_hot else 0
        max_run = max(max_run, current_run)
    reference_run = 0
    for is_hot in reversed(hot.tolist()):
        if not is_hot:
            break
        reference_run += 1
    return {
        "event_window_complete": True,
        "hot_hours_last_24h": int(hot.iloc[-24:].sum()),
        "hot_hours_last_72h": int(hot.sum()),
        "consecutive_hot_hours_at_reference": reference_run,
        "max_consecutive_hot_hours_last_72h": max_run,
    }


def evaluate_month_hour_persistence(
    temperatures: pd.Series,
    reference_time: pd.Timestamp,
    month_hour_thresholds: dict[tuple[int, int], float],
) -> dict[str, int | bool]:
    """Evaluate a complete 72-hour window against each timestamp's own threshold."""
    expected = pd.date_range(end=reference_time, periods=72, freq="h")
    window = temperatures.reindex(expected)
    if not bool(window.notna().all()):
        return {"event_window_complete": False}
    try:
        hot = pd.Series(
            [
                value > month_hour_thresholds[(timestamp.month, timestamp.hour)]
                for timestamp, value in window.items()
            ],
            index=expected,
            dtype=bool,
        )
    except KeyError as error:
        raise ValueError(f"missing month/hour threshold: {error.args[0]}") from error
    runs: list[int] = []
    current = 0
    for is_hot in hot:
        current = current + 1 if is_hot else 0
        runs.append(current)
    reference_run = 0
    for is_hot in reversed(hot.tolist()):
        if not is_hot:
            break
        reference_run += 1
    return {
        "event_window_complete": True,
        "hot_hours_last_24h": int(hot.iloc[-24:].sum()),
        "hot_hours_last_72h": int(hot.sum()),
        "consecutive_hot_hours_at_reference": reference_run,
        "max_consecutive_hot_hours_last_72h": max(runs, default=0),
    }
