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

## Scoped review follow-up: strict JSON and bounded parsing

This follow-up supersedes the YAML input contract and PyYAML runtime concern
described above. Operator input is now strict JSON, which remains a valid Helm
values format but can be parsed entirely with the Python standard library.
Production deployment no longer depends on PyYAML.

The normalizer reads at most 64 KiB before parsing, decodes strict UTF-8, rejects
duplicate keys at every object level with `object_pairs_hook`, rejects
non-standard numeric constants and non-finite floats, and limits the parsed
tree to 32 levels. JSON parsing inherently rejects YAML aliases, anchors, merge
keys, comments, tags, and multiple documents. Every invalid or resource-limit
case exits with the single bounded message:

```text
Invalid additional egress values.
```

The exact accepted shape remains:

```json
{
  "networkPolicy": {
    "additionalEgress": [
      {
        "to": [
          {
            "ipBlock": {
              "cidr": "10.20.0.0/24"
            }
          }
        ]
      }
    ]
  }
}
```

Both production entry points pass only normalized mode-600 JSON to Helm and
remove it through the existing cleanup trap. CI continues to provide the input
over standard input, while manual deployment reads the configured operator
file. The tracked example and operator documentation now consistently use
`deploy/additional-egress-values.example.json` and explicitly require strict
JSON.

### Follow-up TDD evidence

The focused RED run added the resource and dependency regressions before the
implementation:

```bash
PATH="$PWD/.venv/bin:$PATH" .venv/bin/pytest \
  scripts/test_additional_egress_values.py \
  scripts/test_ci_deploy_namespace.py::test_deploy_normalizes_persistent_non_secret_additional_egress_values \
  scripts/test_helm_security_hardening.py::test_operator_additional_egress_example_renders_private_custom_service \
  -v -n 0
```

Result: **21 failed**. The old validator failed immediately without site
packages, leaked a PyYAML import traceback, lacked bounded resource handling,
emitted YAML rather than exact JSON, and left the docs/example on the YAML
contract.

After the stdlib-only implementation and contract updates, the same run
reported **21 passed**. The cases include the original unrestricted overlay,
duplicate keys, YAML aliases/merge and multiple-document input, unknown keys,
empty and wrong types, a 5,000-digit integer, 1,500 nesting levels, invalid
UTF-8, input above 64 KiB, exact generic stderr, isolated `python -S` execution,
mode-600 cleanup, exact normalized JSON, and rendered NetworkPolicy behavior.

The expanded affected suite:

```bash
PATH="$PWD/.venv/bin:$PATH" .venv/bin/pytest \
  scripts/test_additional_egress_values.py \
  scripts/test_ci_deploy_namespace.py \
  scripts/test_helm_security_hardening.py \
  scripts/test_supply_chain_pins.py \
  scripts/test_trivy_workflows.py -q -n 0
```

Result: **73 passed**.

Follow-up verification:

- `make helm-validate` — 17 Helm security tests passed and every chart
  lint/template command completed.
- `make lint` and `make typecheck` — all repository lint, dead-code, formatting,
  Python typechecker, and frontend typecheck gates passed.
- Focused Ruff and format checks, Bash syntax, ShellCheck, workflow YAML
  parsing, stale YAML-contract search, and `git diff --check` passed.
- Staged commit hooks passed, including JSON/YAML checks, secret-key detection,
  Ruff, mypy, ty, pyrefly, Vulture, Prettier, and applicable frontend checks.

No live Helm upgrade or cluster mutation was performed. The parser is
stdlib-only and fails before Helm on invalid, oversized, deeply nested, or
undecodable input.
