# HeatSafe 2030 Deployment

## Accepted Public Topology

The competition product is already deployed. Its primary entry is
<https://heatsafe-2030.pages.dev>; the backup engineering endpoint is
<https://heatsafe-2030.cyrus-ai-lab.workers.dev>.

```text
Browser
  -> Pages Static Assets: /, SPA routes, /assets/*
  -> Pages Function: /health, /api/*
  -> HEATSAFE Service Binding
  -> heatsafe-2030 TypeScript Worker
  -> frozen local artifacts
```

Static assets do not invoke the Pages Function. Dynamic requests retain their
method, path, query, headers, body, response headers, and SSE stream through the
Service Binding.

## Frozen Production Identity

| Item | Value |
| --- | --- |
| Source release | `competition-deploy-v3` (annotated) |
| Release commit | `6d4b36a1174a9f22d03c1b988c1b99341ecf9fb0` |
| Pages deployment | `04ecbd0e-f358-4bbb-82c7-3228e05af1b0` |
| Worker version | `6debc47a-79eb-4b5a-8a64-08423d19b776` |
| Public provider | `NONE` |
| Model API called | NO |

Do not redeploy either component solely to verify the source. A deployment
creates a new public version and requires a separate acceptance cycle.

## Resource Contract

The accepted runtime uses only Cloudflare Workers Free, Pages Static Assets, a
Pages Function, one Service Binding, and free `pages.dev`/`workers.dev`
hostnames. It uses no AI, D1, KV, R2, Durable Objects, Queues, Hyperdrive,
Vectorize, Containers, custom domain, database, or persistent storage.

Required fixed monthly cost is USD 0 within Cloudflare Free account-wide quotas;
this is not an unlimited-usage claim.

## Reproduce and Verify

Worker and frontend:

```bash
cd cloudflare
npm install
npm --prefix frontend install
npm run typecheck
npm run build
npm test
npm --prefix frontend test -- --run
```

Pages front door:

```bash
cd ../pages-frontdoor
npm install
npm test
npm run typecheck
npm run prepare:static
```

The generated Pages assets are intentionally ignored by Git. They are rebuilt
from `cloudflare/frontend/dist`, with the external Google Fonts import removed
from the Pages-only copy.

## Local Development

Start the Worker after building its frontend:

```bash
cd cloudflare
npm run build
npx --no-install wrangler dev
```

The Pages front-door README documents local Service Binding verification. Local
commands must use test/development aliases and must not target production.

## Public Verification Paths

```text
GET  /
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

Unknown `/api/*` paths must return JSON 404, not the SPA shell.

## Reference Docker Path

The root `Dockerfile`, `backend/`, `frontend/`, and `deployment/` directories
preserve the original Python/FastAPI reference implementation. They are useful
for local reproduction and scientific traceability but are not the primary
competition production path.

The root `deployment_manifest.txt` and `deployment_manifest_sha256.txt` are
historical integrity records for `competition-deploy-v1`; they are not manifests
of the later Cloudflare v2/v3 additions.

```bash
docker build -t heatsafe-2030:reference .
docker run --rm -p 8010:8010 --env-file deployment/.env heatsafe-2030:reference
```

No provider configuration is required. Keep the optional provider variables
empty to run the deterministic grounded fallback.

## Change Control

- Never commit credentials, populated `.env` files, Wrangler state, or generated dependencies.
- Never move or rewrite `competition-deploy-v1`, `competition-deploy-v2`, or `competition-deploy-v3`.
- Never force push release history.
- Any future public deployment requires explicit authorization and full public parity, SSE, secret, science, and Free-plan acceptance.
