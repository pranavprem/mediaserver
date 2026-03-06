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
| `proxy` | Cloudflare tunnel access | cloudflared, jellyfin, jellyseerr, plex, vaultwarden, immich-server |
| `immich` | Photo stack (DB/Redis isolated) | immich-server, immich-machine-learning, immich-postgres, immich-redis |
| `management` | Container management | portainer, watchtower, gitea |
| `monitoring` | Observability stack | prometheus, grafana, cadvisor, node-exporter, dozzle |

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
- Media directories (downloads, movies, tv, photos)

---

## Makefile

The Makefile reads `CONFIG_ROOT` from `.env` — no hardcoded paths.

| Target | What it does |
|--------|-------------|
| `make sync-configs` | Copies prometheus.yml + recyclarr.yml to CONFIG_ROOT, fixes permissions, restarts both services |
| `make sync-prometheus` | Syncs just prometheus.yml and restarts Prometheus |
| `make sync-recyclarr` | Syncs just recyclarr.yml and restarts Recyclarr |
| `make update-gluetun` | Pulls latest gluetun image, stops all 5 dependents, recreates gluetun, waits for healthy, restarts dependents |
| `make help` | Shows available targets |

**After editing any config file in the repo:** `git pull && make sync-configs`

**Gluetun updates:** `make update-gluetun` (never use Watchtower for this)

---

## Quick start

### Step 0 — Paths

This guide assumes:
- Compose project folder: `/volume1/docker/mediaserver`
- Config root: `/volume1/media/config`
- Media root: `/volume1/media`

### Step 1 — Create folders

```bash
mkdir -p /volume1/docker/mediaserver
mkdir -p /volume1/media/{downloads,downloads/incomplete,movies,tv,photos}
mkdir -p /volume1/media/config/{gluetun,qbittorrent,sabnzbd,prowlarr,sonarr,radarr,jellyfin,jellyseerr,plex,vaultwarden,portainer,recyclarr,prometheus,gitea}
mkdir -p /volume1/media/config/immich/{postgres,redis,model-cache}
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
openssl rand -base64 32                                    # Immich DB/Redis passwords
docker run --rm -it vaultwarden/server /vaultwarden hash   # Vaultwarden admin token
```

### Step 4 — Deploy

```bash
cd /volume1/docker/mediaserver
docker compose up -d
docker compose ps
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
docker compose restart grafana
```

### Cross-compose monitoring (Oracle)

To scrape metrics from containers in other compose projects (e.g., Oracle trading system), connect their network-parent container to the `monitoring` network:

```bash
docker network connect mediaserver_monitoring <container_name>
```

Then add a scrape job to `prometheus.yml` targeting that container.

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
docker compose ps

# Logs
docker compose logs --tail=200
```

---

## Gitea

LAN-only Git server at `http://NAS_IP:41234`. Set `GITEA_DISABLE_REGISTRATION=true` after creating your admin account.

```bash
git remote add nas http://NAS_IP:41234/username/repo.git
git push nas main
```
