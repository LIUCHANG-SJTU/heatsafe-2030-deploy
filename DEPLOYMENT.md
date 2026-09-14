# HeatSafe 2030 Deployment

## Recommended architecture

Deploy the repository root `Dockerfile` as one stateless service. FastAPI serves
both `/api/v1/...` and the production React build, so the public application uses
one origin and does not require cross-origin access.

```text
Internet -> Cloudflare DNS/HTTPS -> container host -> FastAPI + React
                                             -> frozen local artifacts
                                             -> optional GLM provider
```

No database is needed: the competition service is read-only, has no accounts or
collaborative writes, and does not require persistent chat sessions.

## Build and run

```bash
docker build -t heatsafe-2030:competition .
docker run --rm -p 8010:8010 --env-file deployment/.env heatsafe-2030:competition
```

Copy `deployment/.env.example` to a host-managed secret configuration. Do not add
the resulting file to Git or to the competition ZIP.

Verify these paths after deployment:

```text
GET  /health
GET  /api/v1/demo
GET  /api/v1/demo/grids
GET  /api/v1/agent/status
POST /api/v1/agent/query
POST /api/v1/agent/stream
GET  /api/v1/actions/grid/{grid_id}
GET  /api/v1/actions/hotspots
```

The application does not expose `/api/v1/grids`; the current, tested route is
`/api/v1/demo/grids`.

## Hosting choices

Use any persistent container host such as Railway, Render, Fly.io, Cloud Run, or
a VPS. Configure its health check as `/health`, expose the platform-provided
`PORT`, and store the GLM API key in the platform secret manager.

### Render Web Service

The Render Dashboard values are:

```text
Service type: Web Service
Runtime: Docker
Dockerfile path: ./Dockerfile
Health check path: /health
Persistent disk: none
Database: none
```

Connect the private GitHub repository and select the reviewed deployment branch.
Render builds the root Dockerfile and injects `PORT`; no port value should be
hard-coded in the service settings. Add the optional Agent variables as Render
Secrets, especially `HEATSAFE_AGENT_API_KEY`. A `render.yaml` was intentionally
not added because the dashboard configuration is sufficient and its Blueprint
schema was not needed for this single service.

Cloudflare can provide the custom domain, HTTPS, Web Application Firewall and
per-IP rate limiting. A Cloudflare Tunnel is suitable when the container runs on
a persistent VPS. Do not make the competition URL depend on a personal laptop
remaining online.

Do not port this backend to Cloudflare Python Workers for the submission. The
existing container is the verified deployment boundary and avoids introducing a
new Python/Wasm compatibility surface.

## GitHub and competition delivery

GitHub remains source control, preferably as a private repository. Freeze a
submission commit or tag, then deliver the clean source snapshot and a working
URL; judges should not need Git history or a repository account.

## Production checklist

- Keep the provider key server-side.
- Restrict direct access to the origin when Cloudflare proxies the service.
- Configure an Agent rate limit at the edge.
- Keep one warm instance during judging to avoid cold-start delays.
- Confirm SSE is not buffered by the hosting proxy.
- Verify Chinese and English queries from an external network.
- Rehearse deterministic fallback by temporarily omitting the provider variables.
