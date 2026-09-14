from __future__ import annotations


DATASET_ID = "reanalysis-era5-land-timeseries"
VARIABLES = ("2m_dewpoint_temperature", "2m_temperature")
REQUEST_LONGITUDE = 120.093
REQUEST_LATITUDE = 30.211


def request_for(date_range: str) -> dict:
    return {
        "variable": list(VARIABLES),
        "location": {
            "longitude": REQUEST_LONGITUDE,
            "latitude": REQUEST_LATITUDE,
        },
        "date": [date_range],
        "data_format": "netcdf",
    }
