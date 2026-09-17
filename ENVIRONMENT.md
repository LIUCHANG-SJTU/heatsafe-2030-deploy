# HeatSafe 2030 Environment

## Public Competition Profile

The public product runs on Cloudflare Pages and Workers, not the root Docker
container.

| Component | Environment contract |
| --- | --- |
| Pages Static Assets | Serves `/`, SPA routes, and `/assets/*` |
| Pages Function | Handles only `/health` and `/api/*` |
| Service Binding | `HEATSAFE -> heatsafe-2030` |
| Worker | TypeScript deterministic grounded runtime with frozen local artifacts |

The production configuration is committed in `cloudflare/wrangler.jsonc` and
`pages-frontdoor/wrangler.jsonc`:

```text
PUBLIC_PROVIDER=NONE
AGENT_MODE=DETERMINISTIC_GROUNDED_FALLBACK
```

No secret, API key, database, persistent disk, or paid binding is required.
The public deployment does not call a model API.

## Optional Provider Boundary

The Python reference implementation retains optional support for an
OpenAI-compatible provider such as `glm-5.3-flash`. It is disabled in the public
competition runtime. No provider endpoint or credential belongs in frontend
variables, committed files, or the public Pages/Worker configuration.

| Variable | Applies to | Required publicly | Notes |
| --- | --- | ---: | --- |
| `PUBLIC_PROVIDER` | Cloudflare Worker | yes | Fixed to `NONE` |
| `AGENT_MODE` | Cloudflare Worker | yes | Fixed to `DETERMINISTIC_GROUNDED_FALLBACK` |
| `HEATSAFE_AGENT_PROVIDER` | Python reference | no | Leave empty for deterministic fallback |
| `HEATSAFE_AGENT_BASE_URL` | Python reference | no | Operator-supplied provider endpoint |
| `HEATSAFE_AGENT_MODEL` | Python reference | no | Optional model name |
| `HEATSAFE_AGENT_API_KEY` | Python reference | no | Server-side secret; never commit |
| `PORT` | Python reference container | no | Host-injected; local fallback is 8010 |

Copy `deployment/.env.example` only for local Docker reference testing. Never
commit a populated `.env`, use a secret in a `VITE_` variable, or expose one to
the browser.

## Reproducibility Toolchain

- Node.js and npm build/test the TypeScript Worker, React frontend, and Pages front door.
- Wrangler 4.38.0 is pinned in both Cloudflare packages.
- Python 3.11 and Docker are required only for the reference FastAPI path.
- Frozen JSON/GeoJSON artifacts are committed under both `cloudflare/data/` and the canonical `data/` tree.
- Raw rasters, caches, generated dependencies, Wrangler state, and credentials are intentionally excluded.

The historical unseen-language planning holdout of `12/18` belongs to the
Python research/reference implementation. It is a planning generalization
boundary, not a scientific-model accuracy measure or a public runtime gate.
