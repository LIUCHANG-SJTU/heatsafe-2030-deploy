# HeatSafe 2030

HeatSafe 2030 is a read-only decision-support application for evidence-backed
urban heat-risk comparison. The production service bundles the React dashboard,
FastAPI API, and frozen public-data artifacts in one stateless container.

## Local production run

```bash
docker build -t heatsafe-2030:competition .
docker run --rm -p 8010:8010 heatsafe-2030:competition
```

Open `http://127.0.0.1:8010/`. The service also exposes API documentation at
`/docs` and health status at `/health`.

## Runtime behavior

- No database, persistent disk, or user account is required.
- `DATA_MODE=REAL` uses the frozen HeatSafe demo artifacts bundled under
  `data/processed/`.
- The Agent is read-only and grounded in deterministic tools and Evidence.
- Without provider credentials, Agent requests use the deterministic fallback.
- An optional OpenAI-compatible provider is configured only on the server; its
  API key is never included in the frontend bundle.
- Risk is relative within the selected demo analysis area, not mortality risk,
  causal intervention effect, or an absolute citywide forecast.

## API surface

```text
GET  /health
GET  /api/v1/demo
GET  /api/v1/demo/grids
GET  /api/v1/demo/grids/{grid_id}
GET  /api/v1/actions/hotspots
GET  /api/v1/actions/grid/{grid_id}
GET  /api/v1/agent/status
POST /api/v1/agent/query
POST /api/v1/agent/stream
```

## Deployment

Render can build this repository directly as a Docker Web Service. The service
must listen on `0.0.0.0` and use Render's injected `PORT`; `/health` is the
health-check path. Configure optional provider variables as platform secrets.
See [ENVIRONMENT.md](ENVIRONMENT.md) and [DEPLOYMENT.md](DEPLOYMENT.md).

## Data provenance

The demo artifact and its GeoJSON companion are frozen and hash-audited. Source
dataset metadata is retained under `data/provenance/`. See
`data/provenance/demo_v1/manifest.json` for the demo manifest.
