# Additional egress overlay hardening report

## Outcome

Production CI and `scripts/deploy-local-k8s.sh` no longer pass operator-controlled
additional-egress YAML directly to Helm. Both entry points now use the shared
`prepare_production_additional_egress_file` boundary, which invokes the
repository-owned `scripts/normalize_additional_egress_values.py` validator and
passes only its mode-600 temporary output as a Helm values file.

The validator accepts exactly one YAML document with this structure:

```yaml
networkPolicy:
  additionalEgress:
    - <one or more egress rules>
```

It rejects duplicate keys at every mapping level, anchors, aliases, merge keys,
multiple documents, unknown top-level keys, unknown `networkPolicy` siblings,
empty lists, and non-list values. Consequently, the input cannot change
`production`, `ingress`, `image`, `networkPolicy.enabled`, or
`networkPolicy.publicEgress`. Failures use structural messages without echoing
operator input.

CI supplies `ADDITIONAL_EGRESS_VALUES` over standard input, so the YAML does not
appear in process arguments. The local helper reads
`ADDITIONAL_EGRESS_VALUES_FILE`, but Helm receives only the normalized temporary
file. Existing cleanup removes that file on success, failure, or signal.

## TDD evidence

### RED

The initial focused run was:

```bash
PATH="$PWD/.venv/bin:$PATH" .venv/bin/pytest \
  scripts/test_additional_egress_values.py \
  scripts/test_ci_deploy_namespace.py::test_deploy_normalizes_persistent_non_secret_additional_egress_values \
  -v -n 0
```

Result: **13 failed**. The normalizer was absent, and the deployment integration
test showed that neither production entry point called a normalization boundary.

### GREEN

After the minimal implementation, the same run reported **13 passed**. The
adversarial cases cover the original unrestricted-overlay bypass, multiple YAML
documents, duplicate nested keys, anchors, aliases and merge keys, unknown root
and sibling keys, empty/null/scalar/mapping values, normalized output, expected
NetworkPolicy rendering, and deployment ordering.

The expanded focused run was:

```bash
PATH="$PWD/.venv/bin:$PATH" .venv/bin/pytest \
  scripts/test_additional_egress_values.py \
  scripts/test_ci_deploy_namespace.py \
  scripts/test_helm_security_hardening.py \
  scripts/test_supply_chain_pins.py \
  scripts/test_trivy_workflows.py -v -n 0
```

Result: **66 passed**.

## Verification

- `PATH="$PWD/.venv/bin:$PATH" make helm-validate` — 17 Helm security tests
  passed; default and production chart lint reported zero failures; all template
  renders completed.
- `PATH="$PWD/.venv/bin:$PATH" make lint` — Ruff, Vulture, ESLint, Prettier, and
  dead-code checks passed.
- `PATH="$PWD/.venv/bin:$PATH" make typecheck` — mypy, ty, pyrefly, and the
  frontend typecheck passed.
- Focused Ruff check and format check for the changed Python files passed after
  correcting one formatting-only finding.
- `bash -n` and ShellCheck passed for both changed deployment shell files.
- The CI workflow parsed successfully as YAML.
- A direct shared-library integration check normalized stdin, produced a
  mode-600 file with only the allowed subtree, and removed it during cleanup.
- The staged-file pre-commit hooks passed, including YAML checks, secret-key
  detection, Ruff, mypy, ty, pyrefly, Vulture, and applicable repository checks.
- `git diff --check` passed.

## Review and concerns

The final diff was reviewed against the requested exact-shape boundary. The
original bytes have no path to Helm in either production entry point, and
nested YAML cannot escape the normalized `networkPolicy.additionalEgress`
subtree.

No live Helm upgrade or cluster mutation was performed. Deployment hosts must
continue to provide Python 3 with PyYAML; a missing parser fails closed before
Helm or cluster mutation. PyYAML is already available in the project environment
and through the existing application dependency graph.

An optional full-tree pre-commit sweep also found an existing Ruff `ISC004`
finding in the unrelated, unchanged `scripts/check_live_content_extraction.py`.
The staged-file hook set passed; this change does not modify or absorb that
baseline issue.
