# Self-hosted GitHub Actions runner setup

The CD deploy job runs on a self-hosted GitHub Actions runner installed directly
on the mini PC (production machine). This gives the runner direct access to
`kubectl`, `helm`, and the local Kubernetes cluster — no SSH hop from GitHub's
cloud infrastructure is needed.

## Prerequisites — tools that must be installed

Install these on the mini PC **before** registering the runner.

| Tool | Required version | Install command |
|------|-----------------|-----------------|
| Git  | any recent      | `sudo apt install git` |
| Node.js | 22.x (matches CI) | see [NodeSource](https://github.com/nodesource/distributions) |
| npm  | bundled with Node | — |
| Docker | 24+ | [Docker Engine install guide](https://docs.docker.com/engine/install/) |
| kubectl | matches cluster | [kubectl install](https://kubernetes.io/docs/tasks/tools/) |
| helm | 3.x | [Helm install](https://helm.sh/docs/intro/install/) |

Verify they are accessible to the user that will run the runner:

```bash
git --version
node --version   # should print v22.x
npm --version
docker info
kubectl get nodes
helm version
```

## Step 1 — Register the runner

1. Go to **https://github.com/ioachim-hub/news-dashboard/settings/actions/runners**
2. Click **New self-hosted runner**
3. Select **Linux / x64**
4. Follow the on-screen download and configuration steps:

```bash
mkdir -p ~/actions-runner && cd ~/actions-runner
# Download and extract the runner tarball (copy exact URL from the GitHub UI)
curl -o actions-runner-linux-x64.tar.gz -L <URL_FROM_GITHUB_UI>
tar xzf actions-runner-linux-x64.tar.gz

# Register — use the token shown on the GitHub UI; it expires in 1 hour
./config.sh --url https://github.com/ioachim-hub/news-dashboard \
            --token <REGISTRATION_TOKEN_FROM_GITHUB_UI> \
            --name ioachim-minipc \
            --labels self-hosted
```

Accept the defaults for the work folder (`_work`).

## Step 2 — Install as a systemd service

Run the helper script that ships with the runner to create and enable a systemd
unit. This ensures the runner restarts automatically on reboot.

```bash
cd ~/actions-runner
sudo ./svc.sh install   # creates /etc/systemd/system/actions.runner.*.service
sudo ./svc.sh start
sudo systemctl status "actions.runner.*"
```

Check that the runner appears as **Idle** in the GitHub UI at
`https://github.com/ioachim-hub/news-dashboard/settings/actions/runners`.

To manage the service later:

```bash
sudo systemctl stop    "actions.runner.*"
sudo systemctl start   "actions.runner.*"
sudo systemctl restart "actions.runner.*"
```

## Step 3 — Environment variables and secrets

The deploy workflow reads one GitHub Actions secret. Add it at
**https://github.com/ioachim-hub/news-dashboard/settings/secrets/actions**:

| Secret name  | Description |
|--------------|-------------|
| `GHCR_TOKEN` | A GitHub Personal Access Token (classic) with **`read:packages`** scope only. Used to authenticate Docker and to refresh the Kubernetes imagePullSecret on every deploy. Generate at https://github.com/settings/tokens — set a 1-year expiry and rotate when it expires. |

`GITHUB_TOKEN` is provided automatically by GitHub for the test and publish jobs;
no manual secret is needed for it.

If the GHCR package is made **public** (repo Settings → Packages → Change
visibility), `GHCR_TOKEN` is not required and the `docker login` / `kubectl
create secret` lines in the workflow can be removed.

No environment variables need to be set at the OS level for the runner user
beyond what the tool installs already place in `PATH`. If `kubectl` or `helm`
are not in the runner user's `PATH`, add them to `~/.profile` for that user.

## Step 4 — First-time cluster check

Confirm `kubectl` is pointing at the correct cluster and the namespace exists:

```bash
kubectl get nodes
kubectl create namespace news-dashboard --dry-run=client -o yaml | kubectl apply -f -
```

The `helm upgrade --install ... --create-namespace` flag in the workflow also
creates the namespace automatically on first deploy.

## How the full flow works after setup

```
git push origin main
  └─ test job      (ubuntu-latest)    pytest + tsc/vite build
  └─ publish job   (ubuntu-latest)    docker build + push to GHCR with :<sha>
  └─ deploy job    (self-hosted)
       ├─ docker login ghcr.io
       ├─ docker pull <image>:<sha>
       ├─ kubectl apply imagePullSecret
       ├─ git pull --ff-only (sync chart changes)
       ├─ helm upgrade --set image.tag=<sha>
       ├─ kubectl rollout status --timeout=120s
       └─ curl http://localhost:30088/api/health smoke test
```

The deploy job uses `concurrency: group=deploy-production, cancel-in-progress: false`
so rapid pushes queue rather than race.

## Troubleshooting

**Runner shows Offline in GitHub UI**
```bash
sudo systemctl restart "actions.runner.*"
journalctl -u "actions.runner.*" -n 50
```

**`kubectl` / `helm` not found during deploy**
Add the missing binary's directory to `~/.profile` for the runner user and
restart the runner service.

**Image pull backoff in pods**
```bash
kubectl -n news-dashboard get secret ghcr-pull-secret
# If missing, re-run the workflow or create it manually:
kubectl -n news-dashboard create secret docker-registry ghcr-pull-secret \
  --docker-server=ghcr.io \
  --docker-username=<github-actor> \
  --docker-password=<GHCR_TOKEN>
```

**Helm "release not found" error**
This is harmless — `--install` creates the release on first run.

**Deployment name**
The Helm release name `news-dashboard` + chart name `news-dashboard` produces
`news-dashboard-news-dashboard` for pods and deployments. This is expected
(Helm double-name pattern).
