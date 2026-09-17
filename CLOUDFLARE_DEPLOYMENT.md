# Cloudflare Competition Runtime

Current frozen source release: annotated tag `competition-deploy-v3` at
`6d4b36a1174a9f22d03c1b988c1b99341ecf9fb0`.

The primary competition entry is:

<https://heatsafe-2030.pages.dev>

The backup engineering URL is:

<https://heatsafe-2030.cyrus-ai-lab.workers.dev>

The primary entry uses Pages Static Assets for `/`, SPA routes, and `/assets/*`.
Only `/health` and `/api/*` enter a Pages Function, which calls the frozen
Worker through the `HEATSAFE` Service Binding. The browser does not call the
`workers.dev` hostname. The accepted Pages source is in `pages-frontdoor/`.

The `cloudflare/` subtree contains the accepted Worker component, originally
frozen as `competition-deploy-v2` and included unchanged in v3:

<https://heatsafe-2030.cyrus-ai-lab.workers.dev>

The frozen public Cloudflare version is `6debc47a-79eb-4b5a-8a64-08423d19b776`.
The accepted Pages production deployment is
`04ecbd0e-f358-4bbb-82c7-3228e05af1b0`.

The Pages front door was confirmed directly accessible on the target mainland
network (`MAINLAND_DIRECT_ACCESS = PASS`). Its measured first usable UI time
improved from 4060.7 ms to 2920.1 ms (28.1%). The Pages production copy removes
the external Google Fonts import and uses system font stacks.

## Install and Verify

The Worker and frontend use separate lockfiles. Install both dependency sets before building:

```bash
cd cloudflare
npm install
npm --prefix frontend install
npm run typecheck
npm run build
npm test
npm --prefix frontend test -- --run
```

Expected release gates:

- Cloudflare runtime/parity/static-asset tests: 17/17 pass
- Python to TypeScript differential parity: 37/37 exact, 0 fail
- Frontend tests: 32/32 pass
- TypeScript and production build: pass
- Science hashes: exact values recorded in `RELEASE_MANIFEST.json`

## Local Worker

Build the frontend before starting Wrangler because Workers Static Assets serves `frontend/dist`:

```bash
npm run build
npx --no-install wrangler dev
```

Wrangler normally serves the local Worker at `http://localhost:8787`.

## Pages Front Door

Build the accepted frontend before verifying the reproducible Pages copy:

```bash
cd cloudflare
npm install
npm --prefix frontend install
npm run build
cd ../pages-frontdoor
npm install
npm test
npm run typecheck
npm run prepare:static
```

Generated Pages assets are intentionally excluded from Git. They are produced
from `cloudflare/frontend/dist`; `public/_routes.json` is the only tracked file
under `pages-frontdoor/public/`.

## Operator-Only Deployment

Deployment requires the operator's own authorized Cloudflare account. No credential, token, API key or private key is included in this repository.

```bash
npm run build
npx --no-install wrangler deploy
```

The Pages component is deployed separately from `pages-frontdoor/`. These
commands are documentation only: do not run them to verify the frozen release.

The accepted configuration uses only Workers Free, Workers Static Assets and a free `workers.dev` hostname. It has no AI, D1, KV, R2, Durable Objects, Queues, Containers, Hyperdrive, Vectorize, paid observability, custom-domain or model-provider binding. `PUBLIC_PROVIDER` remains `NONE`.

The Pages front door adds only Pages Static Assets, one Pages Function, and the
`HEATSAFE` Service Binding. It adds no paid binding. The required fixed monthly
cost is USD 0 within Cloudflare Free quotas.

Do not deploy solely to verify this source release. Use `wrangler dev` and the
included parity tests for local verification. A Worker or Pages deployment
changes public state and requires separate authorization and acceptance.
