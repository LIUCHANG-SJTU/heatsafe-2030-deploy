from __future__ import annotations

from typing import Protocol

from app.grid.pilot import PilotGridCell

from .api_backend import WorldPopAPIBackend
from .models import WorldPopGridPopulation


class WorldPopGridBackend(Protocol):
    def fetch_grid(self, cell: PilotGridCell) -> WorldPopGridPopulation: ...


class WorldPopAdapter:
    def __init__(self, backend: WorldPopGridBackend) -> None:
        self.backend = backend

    def acquire_grid(self, cell: PilotGridCell) -> WorldPopGridPopulation:
        return self.backend.fetch_grid(cell)


__all__ = ["WorldPopAPIBackend", "WorldPopAdapter", "WorldPopGridBackend"]

