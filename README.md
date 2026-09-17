# HeatSafe 2030

HeatSafe 2030 is a read-only decision-support product for evidence-grounded
urban heat-risk comparison and action prioritization.

## Live Product

| Purpose | URL |
| --- | --- |
| Primary competition entry | <https://heatsafe-2030.pages.dev> |
| Backup engineering endpoint | <https://heatsafe-2030.cyrus-ai-lab.workers.dev> |

The frozen technical source release is the annotated tag
`competition-deploy-v3` at commit
`6d4b36a1174a9f22d03c1b988c1b99341ecf9fb0`.

## Production Architecture

```text
Browser
  -> Cloudflare Pages Static Assets: /, SPA routes, /assets/*
  -> Pages Function: /health, /api/*
  -> HEATSAFE Service Binding
  -> frozen TypeScript Worker
  -> bundled frozen JSON/GeoJSON
```

The browser uses only the `pages.dev` origin. Static files bypass Pages
Functions; API and Agent requests reach the Worker through Cloudflare's internal
Service Binding. The accepted Worker version is
`6debc47a-79eb-4b5a-8a64-08423d19b776`.

## Product Scope

- 400-grid heat-risk map: 315 analyzable land grids and 85 water-excluded grids.
- H/E/V/A decomposition, hotspot ranking, comparisons, and map actions.
- Evidence-grounded Agent with eight deterministic tools and SSE responses.
- Action Intelligence with validation and supporting Evidence bindings.
- Chinese and English user flows with explicit refusal and scope protection.

Risk is a relative priority within the 5 x 5 km demo analysis area. It is not an
individual health probability, mortality probability, citywide absolute-risk
forecast, or causal intervention-effect prediction.

## Runtime Guarantees

- `PUBLIC_PROVIDER=NONE`; the public deployment makes no model API call.
- `glm-5.3-flash` is retained only as an optional, disabled research provider.
- No database, persistent storage, user account, paid binding, or external map
  provider is required.
- Required fixed monthly platform cost is USD 0 within Cloudflare Free quotas.
- Scientific values are read from frozen, hash-audited artifacts; the public
  runtime does not recompute them.

## Repository Layout

| Path | Role |
| --- | --- |
| `pages-frontdoor/` | Final Pages static front door and Service Binding function |
| `cloudflare/` | Accepted TypeScript Worker, React frontend, fixtures, tests, and frozen runtime data |
| `backend/`, `frontend/`, `data/` | Canonical Python/FastAPI reference implementation and source artifacts |
| `Dockerfile`, `deployment/` | Reproducible local/reference container path; not the primary public deployment |
| `deployment_manifest*.txt` | Historical integrity inventory for the v1 Docker snapshot |

See [CLOUDFLARE_DEPLOYMENT.md](CLOUDFLARE_DEPLOYMENT.md) for the current runtime
and [DEPLOYMENT.md](DEPLOYMENT.md) for verification and change-control details.

## Verify the Frozen Runtime

```bash
cd cloudflare
npm install
npm --prefix frontend install
npm run typecheck
npm run build
npm test
npm --prefix frontend test -- --run

cd ../pages-frontdoor
npm install
npm test
npm run typecheck
```

These commands build and test locally; they do not deploy.

## Reference Docker Implementation

The original Python/FastAPI implementation remains available for local
reproduction and scientific traceability:

```bash
docker build -t heatsafe-2030:reference .
docker run --rm -p 8010:8010 heatsafe-2030:reference
```

Open `http://127.0.0.1:8010/`. This reference path is not the primary
competition URL and is not required by the Cloudflare runtime.

## Public API

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

## Release Lineage

- `competition-deploy-v1`: original Docker/FastAPI snapshot.
- `competition-deploy-v2`: annotated zero-cost TypeScript Worker release.
- `competition-deploy-v3`: annotated final Pages competition front-door release.

The v1, v2, and v3 tags are immutable. Documentation-only updates on `main` do
not change the frozen public Pages or Worker deployments.

## Scientific Integrity

| Artifact | SHA-256 |
| --- | --- |
| JSON | `85a568dc55c14288e9173d42815b4501369093ceda85ceb6edb47fa3e57632da` |
| GeoJSON | `7afb32b7a666cf7020576309c245822e3723085f7b36a83a9433146296ccb8ec` |
