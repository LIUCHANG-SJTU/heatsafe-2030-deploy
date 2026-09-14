# HeatSafe 2030 Environment

## Production profile

- One stateless Docker Web Service; no database or persistent disk.
- FastAPI/Uvicorn backend on Python 3.11 and React/Vite frontend built with Node 22.
- Frozen JSON/GeoJSON artifacts are bundled read-only under `data/processed/`.
- Render supplies `PORT`; the container binds `0.0.0.0` and uses `/health`.

## Variables

No secret is required for deterministic fallback mode. Configure the optional
provider only in the Render environment or another server-side secret manager:

```text
APP_ENV=production
DATA_MODE=REAL
HEATSAFE_AGENT_PROVIDER=openai_compatible
HEATSAFE_AGENT_BASE_URL=https://open.bigmodel.cn/api/paas/v4/
HEATSAFE_AGENT_MODEL=glm-5.3-flash
HEATSAFE_AGENT_API_KEY=<server-side secret>
```

| Variable | Classification | Required | Notes |
|---|---|---:|---|
| `APP_ENV` | public configuration | yes | `production` in the image |
| `DATA_MODE` | public configuration | yes | `REAL` for the frozen competition artifact |
| `PORT` | platform configuration | Render | Injected by Render; do not commit a fixed value |
| `FORWARDED_ALLOW_IPS` | public configuration | no | Trusted proxy range |
| `HEATSAFE_AGENT_PROVIDER` | public configuration | no | Enables live planning when configured |
| `HEATSAFE_AGENT_BASE_URL` | public configuration | no | Provider endpoint |
| `HEATSAFE_AGENT_MODEL` | public configuration | no | Provider model name |
| `HEATSAFE_AGENT_API_KEY` | server secret | no | Keep only in platform secrets |

Copy `deployment/.env.example` for local reference. Never commit a populated
`.env`, place a provider key in a `VITE_` variable, or expose it to the browser.

## Reproducibility

The source snapshot contains the production application and frozen artifacts,
but intentionally excludes the larger research workspace, raw rasters, caches,
and development dependencies. The competition release uses the root Dockerfile;
the Docker build creates the frontend production bundle inside the image.

The historical unseen-language planning holdout remains `12/18`. It is a
planning generalization boundary, not a scientific-model accuracy measure.
