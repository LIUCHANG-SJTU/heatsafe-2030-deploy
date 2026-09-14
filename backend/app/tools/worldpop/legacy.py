from app.tools.base import (
    AcquisitionRequest,
    AcquisitionResult,
    AdapterMetadata,
    DataAdapter,
)


class WorldPopPopulationAdapter(DataAdapter):
    """M0 compatibility wrapper; M1 uses WorldPopAdapter with an explicit backend."""

    metadata = AdapterMetadata(
        dataset="WorldPop Global 2 Population Data via API v2",
        dataset_id="worldpop-api-v2-global2",
        provider="WorldPop",
        source_url="https://api.worldpop.org/v2/",
        purpose="100 m estimated total population exposure",
        license_notes="API declares CC BY 4.0; retain API-specific provenance.",
        acquisition_notes="Use WorldPopAPIBackend; no asserted R2025A/DOI mapping.",
    )

    def acquire(self, request: AcquisitionRequest) -> AcquisitionResult:
        self.not_implemented()


class WorldPopAgeSexAdapter(DataAdapter):
    """M0 compatibility wrapper; M1 uses WorldPopAdapter with an explicit backend."""

    metadata = AdapterMetadata(
        dataset="WorldPop Global 2 age/sex estimates via API v2",
        dataset_id="worldpop-api-v2-global2-agesex",
        provider="WorldPop",
        source_url="https://api.worldpop.org/v2/",
        purpose="Estimated population aged 0-14 and 65+",
        license_notes="API declares CC BY 4.0; retain API-specific provenance.",
        acquisition_notes="Use WorldPopAPIBackend; no asserted R2025A/DOI mapping.",
    )

    def acquire(self, request: AcquisitionRequest) -> AcquisitionResult:
        self.not_implemented()

