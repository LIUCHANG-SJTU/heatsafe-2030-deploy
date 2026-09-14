from app.tools.base import (
    AcquisitionRequest,
    AcquisitionResult,
    AdapterMetadata,
    DataAdapter,
)


class Sentinel2NDVIAdapter(DataAdapter):
    metadata = AdapterMetadata(
        dataset="Sentinel-2 Level-2A Surface Reflectance",
        dataset_id="sentinel-2-l2a",
        provider="ESA / Copernicus",
        source_url="https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S2L2A.html",
        purpose="NDVI and vegetation-coverage proxy for adaptive capacity",
        license_notes="Copernicus Sentinel data accessed through Microsoft Planetary Computer; retain ESA/Copernicus science provenance.",
        acquisition_notes="Use B04/B08 physical reflectance, SCL QA, nearest-neighbor classification alignment, and bounded pilot COG windows.",
    )

    def acquire(self, request: AcquisitionRequest) -> AcquisitionResult:
        self.not_implemented()

