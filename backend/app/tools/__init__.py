from .base import (
    AcquisitionRequest,
    AcquisitionResult,
    AdapterMetadata,
    DataAdapter,
    DataAdapterError,
)
from .era5 import ERA5LandAdapter
from .landsat import LandsatSurfaceTemperatureAdapter
from .sentinel2 import Sentinel2NDVIAdapter
from .worldpop import WorldPopAgeSexAdapter, WorldPopPopulationAdapter

__all__ = [
    "AcquisitionRequest",
    "AcquisitionResult",
    "AdapterMetadata",
    "DataAdapter",
    "DataAdapterError",
    "ERA5LandAdapter",
    "LandsatSurfaceTemperatureAdapter",
    "Sentinel2NDVIAdapter",
    "WorldPopAgeSexAdapter",
    "WorldPopPopulationAdapter",
]
