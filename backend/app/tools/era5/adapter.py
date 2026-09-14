from app.tools.base import AcquisitionRequest, AcquisitionResult, AdapterMetadata, DataAdapter


class ERA5LandAdapter(DataAdapter):
    metadata = AdapterMetadata(
        dataset="ERA5-Land hourly time-series",
        dataset_id="reanalysis-era5-land-timeseries",
        provider="Copernicus Climate Change Service / ECMWF",
        source_url="https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land-timeseries",
        purpose="2 m temperature, dew point, historical baseline, and heat exceedance",
        license_notes="CC-BY terms accepted before M3B acquisition.",
        acquisition_notes=(
            "Use one nearest-grid-point temporal context for pilot_v1; never imply "
            "ERA5-Land provides 250 m spatial meteorology."
        ),
    )

    def acquire(self, request: AcquisitionRequest) -> AcquisitionResult:
        self.not_implemented()
