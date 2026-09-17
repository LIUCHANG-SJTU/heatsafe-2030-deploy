# HeatSafe 2030 Pages Front Door

This project is the minimal Cloudflare Pages front door for the frozen `heatsafe-2030` Worker. Pages serves `/`, SPA routes, and `/assets/*` directly as static assets. Only `/health` and `/api/*` reach the Pages Function and its `HEATSAFE` Service Binding.

It contains no HeatSafe business logic, science data, provider configuration, secrets, database, persistent storage, or paid binding.

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

## Deployment

```bash
npx wrangler pages project create heatsafe-2030 --production-branch main
npm run deploy
```

Only `/health` and `/api/*` invoke the Pages Function. The accepted frontend build is copied from `cloudflare/frontend/dist` into `public/` and served directly by Pages; `prepare:static` removes the measured Google Fonts dependency from this Pages-only copy and uses system font stacks. Generated assets are intentionally not tracked. Only the Pages project may be deployed from this directory. Do not redeploy or modify the downstream Worker.
