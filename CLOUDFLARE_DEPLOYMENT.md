# Cloudflare Competition Runtime

The `cloudflare/` subtree contains the source for the accepted public competition deployment:

<https://heatsafe-2030.cyrus-ai-lab.workers.dev>

The frozen public Cloudflare version is `6debc47a-79eb-4b5a-8a64-08423d19b776`.

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

## Deployment

Deployment requires the operator's own authorized Cloudflare account. No credential, token, API key or private key is included in this repository.

```bash
npm run build
npx --no-install wrangler deploy
```

The accepted configuration uses only Workers Free, Workers Static Assets and a free `workers.dev` hostname. It has no AI, D1, KV, R2, Durable Objects, Queues, Containers, Hyperdrive, Vectorize, paid observability, custom-domain or model-provider binding. `PUBLIC_PROVIDER` remains `NONE`.

Do not deploy solely to verify this source release. Use `wrangler dev` and the included parity tests for local verification. A deployment changes the public Worker version and requires separate authorization.
