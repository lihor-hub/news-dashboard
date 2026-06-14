# Self-hosted runner setup on your-runner

The CD workflow (deploy job) runs on a self-hosted GitHub Actions runner installed
directly on the production machine.  This avoids managing SSH keys and gives the
runner direct access to `kubectl` / `helm` / the local Kubernetes cluster.

## One-time setup (run on your-runner)

### 1. Install the runner

Go to **https://github.com/ioachim-hub/news-dashboard/settings/actions/runners**,
click **New self-hosted runner**, select Linux/x64, and follow the steps shown.
When asked for labels, add `your-runner` (the workflow uses `[self-hosted, your-runner]`).

Install as a systemd service so the runner starts on boot:

```bash
sudo ./svc.sh install
sudo ./svc.sh start
sudo systemctl status actions.runner.*
```

### 2. Confirm kubectl and helm are in PATH for the runner user

```bash
# Switch to the runner user (usually the account that ran the install above)
kubectl get nodes        # should show your cluster
helm version             # should print version
```

If they're not in PATH for the runner user, add them to `~/.bashrc` or `~/.profile`
**for that user** (runners source the login shell's PATH).

### 3. Create a GitHub PAT for GHCR image pulls

The deploy job needs a long-lived token to create the Kubernetes imagePullSecret.
Unlike `GITHUB_TOKEN`, a PAT doesn't expire after the workflow run, so pods that
restart days later can still pull the image.

1. Go to **https://github.com/settings/tokens** → **Generate new token (classic)**
2. Name: `news-dashboard-ghcr-read`
3. Scope: `read:packages` only — nothing else
4. Set expiry (1 year is reasonable; update the secret when it expires)
5. Copy the token

### 4. Add the PAT as a GitHub secret

Go to **https://github.com/ioachim-hub/news-dashboard/settings/secrets/actions**
and add:

| Secret name      | Value                          |
|------------------|--------------------------------|
| `GHCR_READ_TOKEN`| The PAT from step 3            |

That's the only secret the deploy workflow needs.  `GITHUB_TOKEN` is provided
automatically by GitHub for the test and publish jobs.

### 5. Create the Kubernetes namespace (first time only)

```bash
kubectl create namespace news-dashboard --dry-run=client -o yaml | kubectl apply -f -
```

The `helm upgrade --install ... --create-namespace` flag in the workflow does this
automatically, but running it once now confirms `kubectl` is working.

### 6. Make the GHCR package visible to the runner

The workflow's "Refresh GHCR pull secret" step handles cluster-side pull auth
automatically on every deploy.  If you want to test a manual pull first:

```bash
docker login ghcr.io -u ioachim-hub -p <GHCR_READ_TOKEN>
docker pull ghcr.io/ioachim-hub/news-dashboard:latest
```

---

## How the full flow works after setup

```
git push origin main
  └─ test job      (ubuntu-latest)   pytest + tsc/vite build
  └─ publish job   (ubuntu-latest)   docker build + push to GHCR with :<sha>
  └─ deploy job    (your-runner)
       ├─ kubectl apply imagePullSecret (refreshes GHCR_READ_TOKEN in cluster)
       ├─ helm upgrade --set image.tag=<sha>  (exact SHA, never "latest")
       ├─ kubectl rollout status --timeout=120s
       └─ curl /api/health smoke test
```

The deploy job uses `concurrency: group=deploy-production, cancel-in-progress: false`,
so rapid pushes queue rather than racing.

## Troubleshooting

**Runner offline**: `sudo systemctl restart actions.runner.<name>`

**Helm fails with "release not found"**: this is fine — `--install` creates it.

**Image pull backoff**: Check the imagePullSecret was created:
```bash
kubectl -n news-dashboard get secret ghcr-pull-secret
```
If missing, re-run the workflow or create it manually with the PAT.

**Deployment name**: The Helm release name `news-dashboard` + chart name `news-dashboard`
produces the pod/deployment name `news-dashboard-news-dashboard`.  This is expected
(Helm double-name pattern); don't rename without a `helm rename` migration.

## HTTPS / Caddy setup

The app runs as a NodePort service on `localhost:30088`.  To serve it over HTTPS
at `news.example.com` (required for PWA install, service worker, and Basic Auth),
a host-level Caddy reverse proxy is needed.

See **[docs/CADDY_HTTPS_SETUP.md](CADDY_HTTPS_SETUP.md)** for the full walkthrough,
including the Caddyfile (at `deploy/Caddyfile` in this repo), DNS configuration,
router port forwarding, and Let's Encrypt certificate setup.
