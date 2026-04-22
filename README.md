# Very NAS Media Server

I got a NAS and then decided to use it as a media server. In the process, I ended up orchestrating a rather cool stack of docker containers. So here it is. I'm told it's "Very NAS"

---- The readme beyond this point is written by AI ----

Clone this repo onto a fresh NAS, follow the steps in order, and end up with the same working setup.

---

## What this stack does

- Routes **download traffic** through ProtonVPN using `gluetun` + WireGuard
- Uses both **torrents** (qBittorrent) and **Usenet** (SABnzbd) for downloads
- Automates TV + Movies with Sonarr/Radarr, indexers managed by Prowlarr
- **Recyclarr** auto-syncs quality profiles from TRaSH guides
- Request UI with **Jellyseerr** driving Sonarr/Radarr
- Streams via **Jellyfin** and **Plex**
- Self-hosted password manager (**Vaultwarden**) via Cloudflare tunnel
- Self-hosted photos (**Immich**) with ML-powered face recognition and smart search
- Self-hosted documents (**Paperless-ngx**) with OCR (Tesseract), Tika + Gotenberg for Office/PDF parsing
- **Portainer** for container management UI
- **Watchtower** for automatic container updates (gluetun excluded — see below)
- **Gitea** for self-hosted Git (LAN only)
- **Observability stack**: Dozzle (logs), Prometheus + Grafana + cAdvisor + node-exporter (metrics)

---

## Architecture

### Network Isolation

| Network | Purpose | Containers |
|---------|---------|------------|
| `downloads` | VPN-tunneled traffic | gluetun, qbittorrent, sabnzbd, prowlarr, radarr, sonarr, recyclarr |
| `media` | Media streaming & management | jellyfin, jellyseerr, plex, recyclarr |
| `proxy` | Cloudflare tunnel access | cloudflared, jellyfin, jellyseerr, plex, vaultwarden, immich-server, paperless-webserver |
| `immich` | Photo stack (DB/Redis isolated) | immich-server, immich-machine-learning, immich-postgres, immich-redis |
| `paperless` | Document stack (DB/Redis/Gotenberg/Tika isolated) | paperless-webserver, paperless-postgres, paperless-redis, paperless-gotenberg, paperless-tika |
| `management` | Container management | portainer, watchtower, gitea |
| `monitoring` | Observability stack | prometheus, grafana, cadvisor, node-exporter, dozzle |

Homepage (dashboard) spans multiple networks to reach all services for its widgets.

### Security Features

- ✅ All containers have `security_opt: no-new-privileges`
- ✅ All containers have health checks
- ✅ VPN kill switch (gluetun firewall)
- ✅ Docker socket mounted read-only where needed
- ✅ Services depend on healthy upstream containers

### Gluetun & `network_mode: service:gluetun`

Services using `network_mode: "service:gluetun"` share gluetun's network namespace. This means:

- They **cannot publish their own ports** — ports must be exposed via gluetun's `ports:` section
- If gluetun is recreated, all dependent containers get orphaned with a stale network namespace
- **Watchtower cannot safely update gluetun** — use `make update-gluetun` instead (see Makefile section)

---

## Repo structure

**In this repo (committed):**
- `docker-compose.yaml` — the full stack
- `example.env` — template with all variables (no secrets)
- `prometheus.yml` — Prometheus scrape config
- `recyclarr.yml` — Recyclarr quality profiles (API key placeholders on public repo)
- `grafana/` — provisioning configs and dashboard JSONs
- `Makefile` — operational targets (see below)
- `README.md`

**On the NAS (NOT committed):**
- `.env` — real secrets (copy from `example.env`)
- `${CONFIG_ROOT}/*` — service databases, tokens, settings
- Media/document directories (downloads, movies, tv, photos, documents)

---

## Makefile

The Makefile reads `CONFIG_ROOT` from `.env` — no hardcoded paths.

| Target | What it does |
|--------|-------------|
| `make up` | Starts the full mediaserver stack |
| `make down` | Brings the full mediaserver stack down |
| `make restart` | Restarts the full mediaserver stack |
| `make logs` | Tails logs for the full mediaserver stack |
| `make ps` | Shows status for the full mediaserver stack |
| `make sync-configs` | Copies prometheus.yml + recyclarr.yml to CONFIG_ROOT, fixes permissions, restarts both services |
| `make sync-prometheus` | Syncs just prometheus.yml and restarts Prometheus |
| `make sync-recyclarr` | Syncs just recyclarr.yml and restarts Recyclarr |
| `make setup-paperless` | Validates Paperless env vars, creates NAS directories, and starts the Paperless stack |
| `make paperless-up` | Starts the Paperless services |
| `make paperless-down` | Stops the Paperless services |
| `make paperless-restart` | Restarts the Paperless services |
| `make paperless-status` | Shows Paperless container status |
| `make paperless-health` | Shows runtime + health status for the Paperless containers |
| `make paperless-logs` | Tails logs for the Paperless stack |
| `make paperless-reset-perms` | Resets ownership for Paperless web/storage directories |
| `make paperless-backup` | Creates a timestamped Paperless backup under `DOCUMENTS_ROOT/backups/` |
| `make paperless-superuser` | Runs Paperless `createsuperuser` |
| `make paperless-shell` | Opens a shell in the Paperless web container |
| `make update-gluetun` | Pulls latest gluetun image, stops all 5 dependents, recreates gluetun, waits for healthy, restarts dependents |
| `make help` | Shows available targets |

**General stack control:** prefer `make up`, `make down`, `make restart`, `make logs`, and `make ps` over raw `docker compose` commands.

**NAS deployment branch:** this stack is deployed from the Gitea `private` branch on the NAS.

**After updating the repo on the NAS:** `git checkout private && git pull origin private && make sync-configs`

**Gluetun updates:** `make update-gluetun` (never use Watchtower for this)

**Paperless bootstrap:** after filling the Paperless env vars in `.env`, run `make setup-paperless`

**Paperless admin:** use `make paperless-superuser`, `make paperless-status`, `make paperless-health`, `make paperless-logs`, and `make paperless-backup` instead of raw `docker compose` commands

**Paperless OCR default:** this stack sets `PAPERLESS_OCR_MODE=redo` because mobile-scanner PDFs and app uploads can contain broken or partial text layers that `skip` mode will ignore.

---

## Quick start

### Step 0 — Paths

This guide assumes:
- Compose project folder: `/volume1/docker/mediaserver`
- Config root: `/volume1/media/config`
- Media root: `/volume1/media`
- Documents root: `/volume1/media/documents`

If you're updating the existing NAS deployment, make sure you're on the deployed branch first:

```bash
cd /volume1/docker/mediaserver
git checkout private
git pull origin private
```

### Step 1 — Create folders

```bash
mkdir -p /volume1/docker/mediaserver
mkdir -p /volume1/media/{downloads,downloads/incomplete,movies,tv,photos}
mkdir -p /volume1/media/documents/{media,consume,export,backups}
mkdir -p /volume1/media/config/{gluetun,qbittorrent,sabnzbd,prowlarr,sonarr,radarr,jellyfin,jellyseerr,plex,vaultwarden,portainer,recyclarr,prometheus,gitea}
mkdir -p /volume1/media/config/immich/{postgres,redis,model-cache}
mkdir -p /volume1/media/config/paperless/{data,postgres,redis}
```

### Step 2 — Permissions

```bash
# Find your UID/GID
id

# Apply ownership (adjust UID:GID if yours differ from 1000:100)
chown -R 1000:100 /volume1/media
```

### Step 3 — Environment

```bash
cp example.env .env
nano .env
# Fill in all values — VPN creds, API keys, passwords
```

Generate secure passwords:
```bash
openssl rand -base64 32                                    # Immich + Paperless DB/Redis passwords
openssl rand -base64 50                                    # PAPERLESS_SECRET_KEY
docker run --rm -it vaultwarden/server /vaultwarden hash   # Vaultwarden admin token
```

### Step 4 — Deploy

```bash
cd /volume1/docker/mediaserver
make up
make ps
```

### Step 5 — Sync configs

```bash
make sync-configs
```

This copies `prometheus.yml` and `recyclarr.yml` to the right places under `CONFIG_ROOT` and restarts the services.

---

## First-run configuration

### qBittorrent — Set a permanent password!

⚠️ qBit generates a random temp password on every restart until you set one through the WebUI.

```bash
docker logs qbittorrent 2>&1 | grep "temporary password"
```

Log in at `http://NAS_IP:8888` → **Tools → Options → Web UI** → set username/password → **Save**.

### SABnzbd — Internal port

SABnzbd listens on internal port **8080**. Since it uses `network_mode: service:gluetun`, its UI port is published via gluetun's ports section.

### Prowlarr — What it syncs

Prowlarr syncs **indexers only** to Sonarr/Radarr. You must add download clients (qBit + SABnzbd) in Sonarr/Radarr manually.

### Download client priority

In Sonarr/Radarr → Settings → Download Clients:
- **SABnzbd:** Priority **1** (preferred — faster, no seeding)
- **qBittorrent:** Priority **50** (fallback)

### Jellyseerr

Point at Docker host gateway for Sonarr/Radarr URLs:
- Radarr: `http://172.17.0.1:7878`
- Sonarr: `http://172.17.0.1:8989`

Disable "Tag Requests" in Jellyseerr's Radarr settings if requests aren't arriving.

### Vaultwarden

Accessible via Cloudflare tunnel at your configured domain. Use `http://vaultwarden:7777` as the tunnel target (HTTP, not HTTPS — TLS terminates at Cloudflare edge).

1. Set `VAULTWARDEN_SIGNUPS_ALLOWED=true` → create your account → set to `false` → redeploy
2. Enable 2FA in vault settings
3. Optionally disable admin panel: set `VAULTWARDEN_ADMIN_TOKEN=` (empty)

### Immich

Accessible via Cloudflare tunnel and on LAN at `http://NAS_IP:2283`.

**External libraries:** Configure up to 5 via `IMMICH_EXTERNAL_1` through `IMMICH_EXTERNAL_5` in `.env`. Unset variables default to `/dev/null`. After adding, scan via **Administration → External Libraries** in Immich.

**ML container:** Has explicit DNS (`8.8.8.8`, `1.1.1.1`) configured to download models from huggingface.co on first run.

**Mobile app:** Use your tunnel URL as server, or `http://NAS_IP:2283` for faster LAN uploads.

### Paperless-ngx

Accessible via Cloudflare tunnel at your configured domain. Use `http://paperless-webserver:8000` as the tunnel target (HTTP, not HTTPS — TLS terminates at Cloudflare edge).

Recommended first-run flow:
1. Fill in the Paperless env vars in `.env`
2. Run:
   ```bash
   make setup-paperless
   ```
3. Add a public hostname in Cloudflare Tunnel pointing to `http://paperless-webserver:8000`
4. Create your admin account:
   ```bash
   make paperless-superuser
   ```
5. In Paperless, create a separate login for Abhinaya instead of sharing credentials
6. Check health or logs if needed:
   ```bash
   make paperless-status
   make paperless-health
   make paperless-logs
   ```
7. If web uploads ever hit ownership weirdness, run:
   ```bash
   make paperless-reset-perms
   ```
8. Create manual backups any time with:
   ```bash
   make paperless-backup
   ```
9. Test mobile upload from your phone over the tunnel URL before adding any extra Cloudflare Access rules

If existing uploads still are not searchable after changing OCR settings, reprocess them from the Paperless UI after the stack restart. The current document actions use the active OCR settings, so changing the mode first matters.

**Mobile capture while away from home:** the simplest first version is using the Paperless web UI over the tunnel URL and uploading scans/photos there. Once that works, you can optionally add mail ingestion or a phone-friendly app flow.

### Recyclarr

Edit `recyclarr.yml` with your Sonarr/Radarr API keys and run:
```bash
make sync-recyclarr
docker exec recyclarr recyclarr sync
```

Uses v8+ schema — `assign_scores_to` (not the old `quality_profiles`). Reaches Sonarr/Radarr via `http://gluetun:8989` / `http://gluetun:7878`.

---

## Observability

### Dozzle — Container logs
`http://NAS_IP:9999` — real-time log viewer for all containers.

### Prometheus — Metrics
`http://NAS_IP:9090` — scrapes cAdvisor (container metrics), node-exporter (host metrics), itself, and Oracle trading system (if connected).

- Config: `prometheus.yml` in repo → synced to `CONFIG_ROOT/prometheus/` via `make sync-prometheus`
- Retention: 30 days or 5 GB (whichever is hit first)
- ⚠️ Prometheus runs as user `nobody` — config file must be world-readable (`chmod 644`)

### Grafana — Dashboards
`http://NAS_IP:3333` — auto-provisions dashboards from `grafana/dashboards/` and datasource from `grafana/provisioning/`.

Included dashboards:
- **mediaserver.json** — container resources, host metrics, disk usage
- **oracle.json** — IB Gateway health, P&L, trades, API performance, guardrails

⚠️ Dashboard and provisioning files must be world-readable. If dashboards show "Not Found":
```bash
chmod 755 grafana grafana/provisioning grafana/provisioning/dashboards grafana/provisioning/datasources grafana/dashboards
chmod 644 grafana/dashboards/* grafana/provisioning/dashboards/* grafana/provisioning/datasources/*
make sync-grafana
```

### Cross-compose monitoring (Oracle)

To scrape metrics from containers in other compose projects (e.g., Oracle trading system), connect their network-parent container to the `monitoring` network:

```bash
docker network connect mediaserver_monitoring <container_name>
```

Then add a scrape job to `prometheus.yml` targeting that container.

---
---

## Watchtower

Auto-updates containers at 4 AM daily. **Gluetun is excluded** (`watchtower.enable=false`) because recreating gluetun orphans all `network_mode: service:gluetun` containers.

Update gluetun manually:
```bash
make update-gluetun
```

---

## Verification

```bash
# VPN is working
docker exec qbittorrent curl ifconfig.me
# Should show a ProtonVPN IP, not your ISP

# All containers healthy
make ps

# Logs
make logs
```

---

## Gitea

LAN-only Git server at `http://NAS_IP:41234`. Set `GITEA_DISABLE_REGISTRATION=true` after creating your admin account.

For this stack, the NAS deployment tracks the `private` branch from Gitea.

```bash
git remote add nas http://NAS_IP:41234/username/repo.git
git push -u nas private
```
