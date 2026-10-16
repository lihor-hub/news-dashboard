# Python 3.15 development container

Use **Dev Containers: Reopen in Container** in VS Code, or open a Codespace,
for stable CPython 3.15 with Node 26. The project's runtime minimum and
production Dockerfile still target Python 3.14; this environment prepares the
later runtime cutover in #1531.

The image uses official `python:3.15.0-slim-bookworm`, pinned to the
multiarchitecture index
`sha256:122756f3fe72c4f5d3d71897888204ee85774bc79de952555b8a474e1d0a5d53`.
Its Linux amd64 manifest is
`sha256:c1035719031463035de2f9b5ee86b0ab18842ddee18556ee89999f4b38a3c559`;
Linux arm64 is
`sha256:f97898458240000890f4d60cc53c24550fc141f4215e8ee881701e5f8a3ff8a7`.
Both use Debian Bookworm and standard GIL CPython. Microsoft has no 3.15 tag
in its [Python devcontainer registry](https://mcr.microsoft.com/v2/devcontainers/python/tags/list)
as checked on 2026-10-17. The official image supplies Python; the Dockerfile
adds a non-root `vscode` user, Bash, Git, sudo, Make, C/C++ build tools,
PostgreSQL client and Rust 1.95.0 for dependencies that need native builds.
The existing Dev Containers Node feature installs Node 26.

## Open and rebuild

Install Docker with Compose and the VS Code Dev Containers extension, then
open this repository and choose **Reopen in Container**. From a terminal,
the equivalent validation path uses the
[Dev Containers CLI](https://github.com/devcontainers/cli):

```bash
npm install --global @devcontainers/cli@0.89.0
devcontainer build --workspace-folder .
devcontainer up --workspace-folder .
devcontainer exec --workspace-folder . bash .devcontainer/verify.sh
```

The workspace remains `/workspace` and the editor selects
`/workspace/.venv/bin/python`. Compose named volumes hold `.venv` and
`node_modules`, hiding host dependencies without modifying them. Post-create
refuses to run unless those paths are mount points. It clears the isolated
venv with the image's `/usr/local/bin/python`, installs editable runtime/dev
dependencies through ordinary unlocked pip, runs `npm ci`, installs commit
and push hooks, and initializes the development database and source catalog.
Tools are on PATH in terminals, tasks and hooks.

After updating the image, use **Dev Containers: Rebuild Container**, or:

```bash
devcontainer up --workspace-folder . --remove-existing-container
```

This reruns post-create and replaces even a stale Python 3.14 container venv.
Installed container-only packages must be reinstalled. Database data persists
in its separate Compose volume. Do not run `post-create.sh` on the host or
remove database volumes as part of a rebuild. `scripts/bootstrap-worktree.sh`
remains the host-worktree bootstrap; it deliberately preserves existing
venvs and is not the container interpreter migration command.

## Develop and test

Inside the container:

```bash
python -VV
node --version
make lint
make typecheck
make test
make build
python -m uvicorn news_dashboard.main:app --reload --host 0.0.0.0 --port 8080
# In a second terminal:
npm run dev -- --host 0.0.0.0
```

VS Code forwards 8080 and 5173. The non-root workspace user can edit files
and rebuild dependencies. On Linux the Dev Containers tooling updates its UID
to match the host user.

The app connects to the private Compose service `db:5432/news_dashboard`;
tests use `db:5432/news_dashboard_test`, created by `postgres-init.sql` on the
new volume's first start. Compose waits for PostgreSQL readiness before
post-create. It publishes no host database port. Both connections set
`PGOPTIONS='-c max_parallel_workers_per_gather=0'`. Keep these local-only
credentials inside the development environment.

Host tests use a different database: verify both ignored `.env` URLs target
the dedicated `nd-test-pg` at `localhost:55432/news_dashboard_test` as
`news_dashboard`, then run `source .env && make test` with the same PGOPTIONS.
Never aim host tests at native port 5432 or at the container development DB.
A host `.env` mounted with the workspace does not override the Compose
process environment.

## Executable evidence

The `Development container` workflow builds and opens this exact configuration
on native `ubuntu-24.04` (amd64) and `ubuntu-24.04-arm` runners. It executes
post-create, verifies non-root permissions, Python/GIL/Node, both PostgreSQL
connections, initialized sources, hook executables and running backend/frontend
servers. It runs lint, typechecks, full tests, frontend build and all-file
hooks inside the container. Finally it puts a real Python 3.14 venv in the
container volume, rebuilds, verifies the recovered 3.15 environment and reruns
representative integration tests. Artifacts preserve build, install, version,
package-freeze, gate and rebuild logs for each architecture.

This installs `.[dev]`, matching the existing development contract. Optional
all-extras installation and Chromium execution are separate evidence under
#1530; the devcontainer lifecycle does not certify those extras, production
images, security scans or deployment.
