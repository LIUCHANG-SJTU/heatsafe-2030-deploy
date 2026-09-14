FROM node:22-alpine AS frontend-build

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY frontend/index.html frontend/tsconfig.json frontend/vite.config.ts frontend/vitest.config.ts ./
COPY frontend/src ./src
COPY frontend/fixtures ./fixtures
ARG VITE_API_BASE_URL=""
ARG VITE_USE_FIXTURE="false"
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_USE_FIXTURE=${VITE_USE_FIXTURE}
RUN npm run build


FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    DATA_MODE=REAL \
    FRONTEND_DIST_PATH=/workspace/frontend/dist \
    FIXTURE_GRID_PATH=/workspace/data/processed/fixture_grids.json \
    PROVENANCE_PATH=/workspace/data/provenance/fixture_grids.metadata.json \
    WORLDPOP_ARTIFACT_PATH=/workspace/data/processed/worldpop/worldpop_population_2026.json \
    LANDSAT_ARTIFACT_PATH=/workspace/data/processed/landsat/landsat_lst_pilot_2026.json \
    SENTINEL_ARTIFACT_PATH=/workspace/data/processed/sentinel2/sentinel2_vegetation_pilot_2026.json \
    ERA5_TEMPORAL_CONTEXT_PATH=/workspace/data/processed/era5/era5_temporal_context.json \
    HAZARD_ARTIFACT_PATH=/workspace/data/processed/hazard/spatiotemporal_hazard_pilot_2026.json \
    DEMO_ARTIFACT_PATH=/workspace/data/processed/analysis/heatsafe_demo_v1_2026.json

WORKDIR /workspace/backend
COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install --no-cache-dir '.[m1,m2,m3b]'

COPY --from=frontend-build /build/frontend/dist /workspace/frontend/dist
COPY data/processed /workspace/data/processed
COPY data/provenance /workspace/data/provenance
COPY deployment/start.sh /workspace/deployment/start.sh

RUN useradd --create-home --uid 10001 heatsafe \
    && chmod 0555 /workspace/deployment/start.sh \
    && chown -R heatsafe:heatsafe /workspace

USER heatsafe
EXPOSE 8010

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:' + __import__('os').getenv('PORT', '8010') + '/health', timeout=4).read()"

ENTRYPOINT ["/workspace/deployment/start.sh"]
