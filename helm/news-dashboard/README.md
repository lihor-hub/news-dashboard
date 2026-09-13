# News Dashboard Helm chart

## Published releases

Install a versioned chart from GHCR after preparing your deployment values:

```bash
CHART_VERSION="<application-release-version>"
helm upgrade --install news-dashboard oci://ghcr.io/lihor-hub/charts/news-dashboard \
  --version "$CHART_VERSION" \
  --namespace news-dashboard --create-namespace \
  --values ./my-values.yaml
```

Supply authentication and PostgreSQL configuration in your deployment values;
keep credentials in protected files or Kubernetes Secrets. For the production
Ingress deployment, follow the [self-hosting guide](../../docs/SELF_HOSTING.md),
including its explicit `image.digest`, TLS, persistence, and cutover requirements.
An application commit tag alone does not satisfy the production digest guard.

For source builds, replace the OCI reference and `--version` with
`./helm/news-dashboard`. This uses the chart in your checkout.

## Versioning policy

Published chart `version` and `appVersion` both equal the application release
version, without the `v` prefix. A chart configuration fix should use a `fix:`
commit (or `feat:` for new behavior) so the normal release workflow produces a
new version. Documentation-only changes wait for the next application release.
Do not commit generated version bumps: the tracked metadata is the source
fallback, and CI injects the release version only into the packaged chart.

The package's default image tag is the exact commit behind the release tag.
Production installations still supply an immutable registry `image.digest`.
The image pipeline publishes `latest` and commit-SHA tags; the chart does not
assume a `v<version>` image tag exists.

The release job waits up to 30 minutes for that commit's image, then packages
and pushes `news-dashboard-<version>.tgz` to `oci://ghcr.io/lihor-hub/charts`.
An unavailable image fails the job without publishing its chart. If this wait
times out, fix or finish image publication and rerun the failed release job;
rerunning the entire release workflow finds the existing tag and creates no
new release.
