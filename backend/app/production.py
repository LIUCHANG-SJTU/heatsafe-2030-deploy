from __future__ import annotations

import os
from pathlib import Path

from fastapi.staticfiles import StaticFiles

from app.main import app


DEFAULT_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
frontend_dist = Path(os.getenv("FRONTEND_DIST_PATH", DEFAULT_FRONTEND_DIST))

if not frontend_dist.is_dir():
    raise RuntimeError(
        f"Frontend production build not found at {frontend_dist}. "
        "Run `npm ci && npm run build` in frontend/ before starting app.production."
    )

# API and documentation routes are registered first by app.main. The root mount
# then serves the built dashboard from the same origin without requiring CORS.
app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
