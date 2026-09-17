# HeatSafe 2030 Pages Front Door

This project is the minimal Cloudflare Pages front door for the frozen `heatsafe-2030` Worker. Pages serves `/`, SPA routes, and `/assets/*` directly as static assets. Only `/health` and `/api/*` reach the Pages Function and its `HEATSAFE` Service Binding.

It contains no HeatSafe business logic, science data, provider configuration, secrets, database, persistent storage, or paid binding.

## Production Identity

| Item | Value |
| --- | --- |
| Primary URL | <https://heatsafe-2030.pages.dev> |
| Pages deployment | `04ecbd0e-f358-4bbb-82c7-3228e05af1b0` |
| Downstream Worker | `heatsafe-2030` |
| Worker version | `6debc47a-79eb-4b5a-8a64-08423d19b776` |
| Frozen source release | `competition-deploy-v3` |

## Local verification

```bash
cd ../cloudflare
npm install
npm --prefix frontend install
npm run build
cd ../pages-frontdoor
npm install
npm test
npm run typecheck
npm run prepare:static
npx wrangler dev --cwd ../cloudflare --name heatsafe-2030-service-local
npm run dev
```

Run the Worker and Pages commands in separate terminals. The local-only Worker alias avoids a development registry name collision between the Pages project and its downstream service; the deployed binding still targets `heatsafe-2030`. Deployment requires the operator's own authorized Cloudflare account.

## Operator-Only Deployment

```bash
npm run deploy
```

The Pages project already exists. Do not create or deploy it solely to verify
this source release. Deployment requires the operator's own authorized
Cloudflare account and a new public acceptance cycle.

Only `/health` and `/api/*` invoke the Pages Function. The accepted frontend build is copied from `cloudflare/frontend/dist` into `public/` and served directly by Pages; `prepare:static` removes the measured Google Fonts dependency from this Pages-only copy and uses system font stacks. Generated assets are intentionally not tracked. Only the Pages project may be deployed from this directory. Never redeploy or modify the downstream Worker from this project.
