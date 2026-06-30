# Self-hosted runner setup — moved

This file is kept for historical bookmarks only.

The canonical, up-to-date self-hosted runner setup guide is
**[docs/runner-setup.md](runner-setup.md)**.

That guide reflects the current workflow configuration:

- Runner label: `self-hosted` (see `.github/workflows/ci.yml` deploy job `runs-on: [self-hosted]`)
- Required secret: `GHCR_TOKEN` (not `GHCR_READ_TOKEN`)

Production HTTPS routing is documented against the single source-of-truth
Caddy config at `deploy/Caddyfile`.
