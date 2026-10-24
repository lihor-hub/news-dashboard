# PR previews

Every pull request that touches the app gets a full-stack Vercel preview on a
`*.vercel.app` domain. The frontend and the backend are both built from the
PR branch. Production (`news.lihor.ro`, Helm on Kubernetes) is unaffected,
and Vercel never deploys `main`.

## For contributors

- The Vercel bot posts the preview link on your PR. Sign in with
  `guest` / `demo`.
- The preview runs your branch's backend in `DEMO_MODE`, with seeded sample
  articles, so backend and API changes show up too.
- The guest account is **read-only**. Saving, starring, settings changes and
  other writes return `403 Guest accounts cannot modify data`.
- The data is disposable. The backend scales to zero after about 30 seconds
  without traffic, and each cold start resets to the seeded state. The first
  request after a pause takes a few seconds.
- No AI keys, email, ingest or MCP are configured, so those features are
  absent or inert.
- PRs that change none of the files listed in
  [`deploy/vercel/ignore-build.sh`](../deploy/vercel/ignore-build.sh) skip the
  preview build. That covers docs-only, website-only, desktop-only and
  Android-only changes, for example.

## How it works

[`vercel.json`](../vercel.json) uses Vercel
[Services](https://vercel.com/docs/services):

| Service | What | Routes |
|---------|------|--------|
| `app` | Static SPA: `npm run build` → `frontend/dist`, SPA fallback to `/index.html` | everything else |
| `api` | [Container](https://vercel.com/docs/functions/runtimes/container) from [`deploy/vercel/Dockerfile`](../deploy/vercel/Dockerfile) | `/api/*`, `/auth/*`, `/email/*` |

The `api` image reuses the production Dockerfile's Python 3.15 build without
the frontend. It adds a throwaway PostgreSQL 16 + pgvector inside the
container. [`demo-entrypoint.sh`](../deploy/vercel/demo-entrypoint.sh)
initialises and seeds that database at **image build time**. At runtime it
copies the database to `/tmp`, starts PostgreSQL on a Unix socket, and runs
uvicorn on `$PORT` (default 80). `SESSION_SECRET` is generated per image at
build time and never committed.

Because Vercel serves the SPA and the API on the same preview host, the
browser is same-origin with the API. The session cookie and the CSRF origin
guard work unchanged. No CORS or allowlist configuration is needed.

### Node.js version

The Vercel build image offers Node.js 24.x, so `package.json` allows
`>=24 <27`. CI and the production Docker image still build on Node 26. The
non-required **Frontend build (Node 24)** CI job keeps the lower bound
working.

## Vercel project setup

The Vercel project is `news-dashboard` in the `ioachim-lihors-projects`
scope, connected through the Vercel GitHub App. To set it up again:

1. **Add New → Project**, import `lihor-hub/news-dashboard`, and keep the
   root directory at the repository root. Leave the dashboard build overrides
   off, because `vercel.json` defines both services.
2. Set **Node.js Version** to 24.x.
3. No environment variables are needed.
4. Optional: make the **Vercel** status check required in branch protection.

## Security notes

- Previews are public demo deployments. Run them only with seeded sample
  data, and never point them at a real database or add secrets.
- The guest account is read-only (`reject_guest_writes`). No admin account
  exists, because `BOOTSTRAP_ADMIN_*` is unset and Keycloak is disabled.
- The container runs uvicorn as root, because Vercel routes to port 80.
  PostgreSQL runs as the `postgres` user and listens only on a Unix socket.
  The instance is an ephemeral, isolated Vercel function.
- Vercel serves the static `app` service without the backend's
  Content-Security-Policy header.
