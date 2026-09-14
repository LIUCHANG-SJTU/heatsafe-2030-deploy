from app.tools.base import (
    AcquisitionRequest,
    AcquisitionResult,
    AdapterMetadata,
    DataAdapter,
)


class LandsatSurfaceTemperatureAdapter(DataAdapter):
    metadata = AdapterMetadata(
        dataset="Landsat Collection 2 Level-2 Surface Temperature",
        dataset_id="landsat-c2-l2",
        provider="U.S. Geological Survey",
        source_url="https://www.usgs.gov/landsat-missions/landsat-collection-2-surface-temperature",
        purpose="Urban land-surface-temperature spatial pattern",
        license_notes="USGS Landsat no-cost open data; accessed through Microsoft Planetary Computer.",
        acquisition_notes="Use STAC discovery, AOI QA screening, signed COG window reads, and retained provenance.",
    )

    def acquire(self, request: AcquisitionRequest) -> AcquisitionResult:
        self.not_implemented()

