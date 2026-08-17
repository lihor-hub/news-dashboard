# CI typecheck repair design

## Goal

Restore CI type checking after current dependencies expose `httpx2` response
types, and reduce only CI work that duplicates required coverage.

## Design

- Make every CI job install the Python dependency graph recorded in `uv.lock`.
- Keep the existing behavioral tests; the defect is CI resolving a graph that
  differs from the repository's locked dependencies, not redundant coverage.
- Diagnose the MCP container-smoke job independently and repair it only when
  it is reproducible from the current workflow.
- Remove a CI check only if another required job runs the same command over the
  same inputs for the same pull-request events.

## Verification

Run the affected tests and backend type check locally, then the relevant
repository gates. Confirm the repaired PR's required GitHub checks pass.
