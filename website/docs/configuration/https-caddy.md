---
title: HTTPS with Caddy
sidebar_position: 3
---

# Caddy HTTPS setup for news.lihor.ro

This document covers everything needed to put `news.lihor.ro` behind Caddy on
the mini PC so the app is served over HTTPS.  HTTPS is required for:

- Chrome/Android PWA install prompt ("Add to Home Screen" → standalone app)
- iOS Safari "Add to Home Screen" fullscreen mode
- Service worker registration (browsers enforce secure context)

The app already runs as a Kubernetes NodePort service on `localhost:30088`.
Caddy runs on the host (outside Kubernetes), listens on ports 80/443, obtains a
free Let's Encrypt certificate automatically, and forwards requests to the app.

Authentication is handled by the application itself (see `POST /api/auth/login`).

---

## Prerequisites — things only you can do

Before running any commands on the mini PC you need to complete these steps
through your router and domain registrar.  They cannot be scripted.

### Step 1 — Find your home's public IP address

On the mini PC (or any device on the same network):

```bash
curl -s https://ifconfig.me
```

Write this IP down — you will need it for Step 2.  If your ISP changes it
periodically (dynamic IP), see the DDNS note at the bottom of this document.

### Step 2 — Create a DNS A record for news.lihor.ro

Log in to wherever you manage the `lihor.ro` domain (your DNS registrar or
hosting panel) and add:

| Type | Name | Value               | TTL  |
|------|------|---------------------|------|
| A    | news | `<your-public-IP>`  | 300  |

`news` is the subdomain; `lihor.ro` is added automatically by the registrar.
TTL 300 (5 minutes) lets you update it quickly if the IP changes.

To verify the record has propagated (wait a few minutes, then run):

```bash
dig +short news.lihor.ro          # should print your public IP
# or on Windows:
nslookup news.lihor.ro
```

### Step 3 — Open port 443 on your router (port forwarding)

Log in to your home router admin panel (usually `http://192.168.1.1` or
`http://192.168.0.1`) and add a port-forwarding rule:

| Setting          | Value                              |
|------------------|------------------------------------|
| External port    | 443 (HTTPS)                        |
| Internal IP      | the mini PC's LAN IP               |
| Internal port    | 443                                |
| Protocol         | TCP                                |

You can find the mini PC's LAN IP with `hostname -I` on the mini PC.

Also forward port **80** (HTTP → 80) — Caddy needs it to complete the Let's
Encrypt HTTP-01 challenge on the first run, then redirects all traffic to HTTPS
automatically.

> **Note:** Some ISPs block inbound port 80/443 on residential connections.
> If Let's Encrypt fails with a timeout, see the "Troubleshooting" section.

---

## Installing and configuring Caddy on the mini PC

Run all commands below **on the mini PC** (not in the cluster or a container).

### Step 4 — Install Caddy

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy
```

Verify the install:

```bash
caddy version
sudo systemctl status caddy    # should show "active (running)"
```

### Step 5 — Deploy the Caddyfile

Copy the production Caddyfile from the repo to the system Caddy config location:

```bash
# From the repo root on the mini PC:
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
```

### Step 6 — Reload Caddy

```bash
sudo systemctl reload caddy
# or, to apply config changes and watch for errors:
sudo caddy reload --config /etc/caddy/Caddyfile
```

Caddy will immediately request a Let's Encrypt certificate for `news.lihor.ro`.
Watch the logs to confirm:

```bash
sudo journalctl -u caddy -f
```

You should see a line like `certificate obtained successfully`.  This takes
10–30 seconds on the first run.

### Step 7 — Verify

```bash
curl https://news.lihor.ro/api/health
# Expected: {"status":"ok","database":"PostgreSQL",...}
```

Open `https://news.lihor.ro` in Chrome on your phone — you should see a padlock
and the login page.  After logging in, you should see the dashboard, and after a
few seconds, an install prompt or the option in the browser menu to "Add to Home
Screen" as a standalone app (no browser chrome).

---

## Keeping the Caddyfile in sync with the repo

The `deploy/Caddyfile` in this repo is the only production source of truth for
the `news.lihor.ro` Caddy config. It includes the app NodePort proxy, the
same-host `/keycloak` proxy, compression, and browser security headers.
After any change, copy it to the mini PC and reload:

```bash
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

---

## Dynamic IP / DDNS (if your public IP changes)

Residential ISPs often assign a new public IP when the router reboots.  If the
DNS A record goes stale, the certificate renewal and site access both break.

Options:

1. **Check periodically**: run `curl -s https://ifconfig.me` and update the DNS
   record if it changed.
2. **DDNS client**: most routers have a built-in DDNS client that updates a
   provider (DuckDNS, No-IP, Cloudflare) automatically.  If `lihor.ro` is on
   Cloudflare, the Cloudflare DDNS client can keep the A record current with
   zero manual effort.
3. **Static IP**: ask your ISP for a static residential IP (usually a small
   monthly fee).

---

## Troubleshooting

**`/auth/login` shows the dashboard login shell instead of redirecting to Keycloak**
The service worker is probably serving the SPA fallback for an auth route. Keep `vite.config.ts` configured with `navigateFallbackDenylist` entries for `/api/`, `/auth/`, and `/keycloak/`, then rebuild/redeploy. On a phone/PWA, close and reopen the installed app or clear site data once so the new service worker activates.

**Caddy logs ACME errors for `keycloak.lihor.ro`**
Do not import a separate `keycloak.lihor.ro` site unless DNS exists. The supported local deployment exposes Keycloak at `https://news.lihor.ro/keycloak`, so disable or rename the separate Caddyfile, validate, and reload Caddy:

```bash
sudo mv /etc/caddy/Caddyfile.d/keycloak.lihor.ro.caddyfile \
  /etc/caddy/Caddyfile.d/keycloak.lihor.ro.caddyfile.disabled
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

**`caddy reload` shows a config error**
Run `caddy validate --config /etc/caddy/Caddyfile` to see the exact error.

**Let's Encrypt certificate request times out**
Caddy uses HTTP-01 challenge by default, which requires port 80 to be reachable
from the internet.  Check:
- Port 80 is forwarded on the router (Step 3)
- Your ISP doesn't block inbound port 80 (try `curl http://news.lihor.ro` from
  a mobile data connection, not Wi-Fi)
- The DNS A record has propagated (`dig +short news.lihor.ro` returns your IP)

If port 80 is blocked, switch to DNS-01 challenge — this requires a Cloudflare
API token if `lihor.ro` is on Cloudflare.  See
https://caddyserver.com/docs/automatic-https#dns-challenge.

**Chrome still shows "Add to Bookmark" instead of "Install"**
Open DevTools → Application → Manifest and check the "Installability" section.
Common remaining issues:
- The service worker hasn't activated yet — visit the page, wait 10 seconds,
  then close and reopen it
- A previous visit cached a non-HTTPS version — clear site data in Chrome
  settings and try again
