# HeatSafe 2030 Cloudflare Competition Release

This directory is the source for the accepted zero-cost public competition runtime deployed at:

<https://heatsafe-2030.cyrus-ai-lab.workers.dev>

The accepted Cloudflare version is `6debc47a-79eb-4b5a-8a64-08423d19b776`.

## Runtime

- Cloudflare Workers Free with Workers Static Assets
- TypeScript deterministic grounded runtime
- React/Vite frontend with MapLibre GL JS 6.9.0
- Eight public tools backed only by bundled frozen JSON and GeoJSON
- Request-local Evidence Ledger, deterministic renderer, validator, Action Intelligence and SSE
- `PUBLIC_PROVIDER=NONE`; `glm-5.3-flash` remains an optional disabled provider
- No model API call, database, persistent storage, paid binding, custom domain or external map provider

## Accepted Results

- Python to TypeScript parity: 37/37 exact, 0 fail
- Public Agent: 19/19 exact
- Public Action API: 2/2 exact
- Public SSE: 3/3 exact
- Frontend: 32/32 pass
- Science grid counts: 400 total, 315 analyzable land, 85 water-excluded
- Cloudflare CPU across 121 successful requests: P50 0.690 ms, P99 4.773 ms, maximum 5.882 ms, 0 errors
- Required fixed monthly platform cost: USD 0 within Workers Free account-wide quotas

## Science Artifacts

- JSON SHA-256: `85a568dc55c14288e9173d42815b4501369093ceda85ceb6edb47fa3e57632da`
- GeoJSON SHA-256: `7afb32b7a666cf7020576309c245822e3723085f7b36a83a9433146296ccb8ec`

Risk values are read from these frozen artifacts. The public runtime does not recompute scientific inputs or risk scores.

## MapLibre Production Fix

Public browser acceptance found that MapLibre 6.9.0's module worker was initially routed through the SPA fallback. The production build now bundles `maplibre-gl-worker` and emits its required `maplibre-gl-shared.mjs` dependency under the exact relative filename expected by MapLibre. Both assets are served from the same Worker Static Assets deployment with JavaScript MIME types. No paid or external map provider is used.

## Credentials

No Cloudflare credential, OAuth token, API key or private key belongs in this release. Deployment requires the operator's own authorized Cloudflare account.
