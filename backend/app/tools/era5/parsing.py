from __future__ import annotations

from dataclasses import dataclass
import io
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd
import xarray as xr

from .temperature import kelvin_to_celsius


TEMPERATURE_ALIASES = ("t2m", "2m_temperature")
DEWPOINT_ALIASES = ("d2m", "2m_dewpoint_temperature")
TIME_ALIASES = ("valid_time", "time")


@dataclass(frozen=True)
class ParsedERA5Point:
    frame: pd.DataFrame
    latitude: float
    longitude: float
    temperature_variable: str
    dewpoint_variable: str
    time_coordinate: str
    temperature_units: str
    dewpoint_units: str


def _find_name(dataset: xr.Dataset, aliases: tuple[str, ...], kind: str) -> str:
    for alias in aliases:
        if alias in dataset.variables or alias in dataset.coords:
            return alias
    for name, variable in dataset.data_vars.items():
        text = " ".join(
            str(variable.attrs.get(field, ""))
            for field in ("standard_name", "long_name")
        ).lower()
        if kind == "temperature" and "2 metre temperature" in text:
            return name
        if kind == "dewpoint" and "2 metre dewpoint" in text:
            return name
    raise ValueError(f"ERA5 NetCDF lacks {kind} field")


def parse_era5_point(path: Path) -> ParsedERA5Point:
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            members = [name for name in archive.namelist() if name.lower().endswith(".nc")]
            if len(members) != 1:
                raise ValueError("ERA5 response ZIP must contain exactly one NetCDF artifact")
            with xr.open_dataset(
                io.BytesIO(archive.read(members[0])), engine="h5netcdf"
            ) as opened:
                dataset = opened.load()
    else:
        with xr.open_dataset(path, engine="h5netcdf") as opened:
            dataset = opened.load()
    try:
        temperature_name = _find_name(dataset, TEMPERATURE_ALIASES, "temperature")
        dewpoint_name = _find_name(dataset, DEWPOINT_ALIASES, "dewpoint")
        time_name = _find_name(dataset, TIME_ALIASES, "time")
        temperature = dataset[temperature_name].squeeze(drop=True)
        dewpoint = dataset[dewpoint_name].squeeze(drop=True)
        temperature_units = str(temperature.attrs.get("units", ""))
        dewpoint_units = str(dewpoint.attrs.get("units", ""))
        if temperature_units.lower() not in {"k", "kelvin"}:
            raise ValueError(f"unexpected temperature units: {temperature_units}")
        if dewpoint_units.lower() not in {"k", "kelvin"}:
            raise ValueError(f"unexpected dewpoint units: {dewpoint_units}")
        times = pd.DatetimeIndex(pd.to_datetime(dataset[time_name].values, utc=True))
        temperature_values = np.asarray(temperature.values, dtype=float).reshape(-1)
        dewpoint_values = np.asarray(dewpoint.values, dtype=float).reshape(-1)
        if not (len(times) == len(temperature_values) == len(dewpoint_values)):
            raise ValueError("ERA5 variables do not align with the time coordinate")
        latitude = float(np.asarray(dataset["latitude"].values).reshape(-1)[0])
        longitude = float(np.asarray(dataset["longitude"].values).reshape(-1)[0])
    finally:
        dataset.close()
    frame = pd.DataFrame(
        {
            "air_temperature_k": temperature_values,
            "dewpoint_temperature_k": dewpoint_values,
            "air_temperature_c": kelvin_to_celsius(temperature_values),
            "dewpoint_temperature_c": kelvin_to_celsius(dewpoint_values),
        },
        index=times,
    ).sort_index()
    if frame.index.has_duplicates:
        raise ValueError("ERA5 time coordinate contains duplicates")
    return ParsedERA5Point(
        frame=frame,
        latitude=latitude,
        longitude=longitude,
        temperature_variable=temperature_name,
        dewpoint_variable=dewpoint_name,
        time_coordinate=time_name,
        temperature_units=temperature_units,
        dewpoint_units=dewpoint_units,
    )
