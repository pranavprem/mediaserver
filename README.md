# Very NAS Media Server

I got a NAS and then decided to use it as a media server. In the process, I ended up orchestrating a rather cool stack of docker containers. So here it is. I'm told it's "Very NAS"

---- The readme beyond this point is written by AI ----

Clone this repo onto a fresh NAS, follow the steps in order, and end up with the same working setup.

---

## What this stack does

- Routes **download traffic** through ProtonVPN using `gluetun` + WireGuard
- Uses both **torrents** (qBittorrent) and **Usenet** (SABnzbd) for downloads
- Automates TV + Movies with Sonarr/Radarr, indexers managed by Prowlarr
- Adds **Whisparr** with a dedicated `/adult` library path so adult media stays separate from movies/TV
- Adds **Stash** for local adult library browsing/metadata and **Stasharr Portal** for Whisparr-backed scene requests
- Adds **Bazarr** for subtitle automation, with a default English + Spanish profile bootstrap
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
| `downloads` | VPN-tunneled traffic | gluetun, qbittorrent, sabnzbd, prowlarr, radarr, whisparr, sonarr, bazarr, recyclarr, stasharr |
| `media` | Media streaming & management | jellyfin, jellyseerr, plex, stash, stasharr, stasharr-postgres, recyclarr |
| `proxy` | Cloudflare tunnel access | cloudflared, jellyfin, jellyseerr, plex, stash, stasharr, vaultwarden, immich-server, paperless-webserver |
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
- `scripts/setup_stasharr.py` — one-shot Stash + Stasharr Portal bootstrap
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
| `make sync-configs` | Copies prometheus.yml + renders recyclarr.yml into CONFIG_ROOT, then refreshes affected services |
| `make sync-prometheus` | Syncs just prometheus.yml and restarts Prometheus |
| `make sync-recyclarr` | Renders recyclarr.yml with live Sonarr/Radarr API keys and ensures Recyclarr is running |
| `make recyclarr-preview` | Previews a TRaSH sync without changing Sonarr/Radarr |
| `make setup-recyclarr` | One-shot Recyclarr setup: render config and apply TRaSH profiles |
| `make setup-bazarr` | Starts Bazarr, wires Sonarr/Radarr using live API keys, and seeds default English + Spanish subtitles |
| `make setup-stasharr` | One-shot Stash + Stasharr Portal bootstrap: creates local-only secrets if needed, wires Whisparr/Stash/StashDB, and queues the first Stash scan |
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
| `make update-gluetun` | Pulls latest gluetun image, stops all gluetun dependents, recreates gluetun, waits for healthy, restarts dependents |
| `make help` | Shows available targets |

**General stack control:** prefer `make up`, `make down`, `make restart`, `make logs`, and `make ps` over raw `docker compose` commands.

**NAS deployment branch:** this stack is deployed from the Gitea `private` branch on the NAS.

**After updating the repo on the NAS:** `git checkout private && git pull origin private && make sync-configs`

**If you're adding Bazarr to an existing deployment:** run `make setup-bazarr` once after pulling.

**If you're enabling the adult request stack:** run `make setup-stasharr` once after pulling. That target writes any missing local-only Stasharr secrets into your local `.env`, enables the `stasharr` compose profile for future `make up/down`, creates the Whisparr `/adult` root folder, and bootstraps the app end-to-end.

**Gluetun updates:** `make update-gluetun` (never use Watchtower for this)

**Paperless bootstrap:** after filling the Paperless env vars in `.env`, run `make setup-paperless`

**Paperless separate scanner intake share:** set `PAPERLESS_INTAKE_PATH` in `.env` if you want the Paperless consume/inbox folder on a different NAS share than `DOCUMENTS_ROOT`.

**Paperless admin:** use `make paperless-superuser`, `make paperless-status`, `make paperless-health`, `make paperless-logs`, and `make paperless-backup` instead of raw `docker compose` commands

**Paperless OCR default:** this stack sets `PAPERLESS_OCR_MODE=redo` because mobile-scanner PDFs and app uploads can contain broken or partial text layers that `skip` mode will ignore.

**Paperless scanner share tuning:** if a scanner writing over SMB triggers `File not found` races in the consume folder, start with `PAPERLESS_CONSUMER_INOTIFY_DELAY=10`. If that is still flaky, switch to polling with `PAPERLESS_CONSUMER_POLLING`.

---

## Quick start

### Step 0 — Paths

This guide assumes:
- Compose project folder: `/volume1/docker/mediaserver`
- Config root: `/volume1/media/config`
- Media root: `/volume1/media`
- Documents root: `/volume1/media/documents`
- Paperless intake path: defaults to `/volume1/media/documents/consume` (or override with `PAPERLESS_INTAKE_PATH`, for example `/volume1/paperless/consume`)

If you're updating the existing NAS deployment, make sure you're on the deployed branch first:

```bash
cd /volume1/docker/mediaserver
git checkout private
git pull origin private
```

### Step 1 — Create folders

```bash
mkdir -p /volume1/docker/mediaserver
mkdir -p /volume1/media/{downloads,downloads/incomplete,movies,tv,adult,photos}
mkdir -p /volume1/media/documents/{media,consume,export,backups}
# If you want scanner intake on a separate shared folder instead:
# mkdir -p /volume1/media/documents/{media,export,backups}
# mkdir -p /volume1/paperless/consume
mkdir -p /volume1/media/config/{gluetun,qbittorrent,sabnzbd,prowlarr,sonarr,radarr,whisparr,bazarr,jellyfin,jellyseerr,plex,vaultwarden,portainer,recyclarr,prometheus,gitea}
mkdir -p /volume1/media/config/stash/{config,metadata,cache,blobs,generated}
mkdir -p /volume1/media/config/stasharr/{app,postgres}
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

Prowlarr syncs **indexers only** to Sonarr/Radarr/Whisparr. You must add download clients (qBit + SABnzbd) in Sonarr/Radarr/Whisparr manually.

### Download client priority

In Sonarr/Radarr/Whisparr → Settings → Download Clients:
- **SABnzbd:** Priority **1** (preferred — faster, no seeding)
- **qBittorrent:** Priority **50** (fallback)

### Whisparr + Jellyfin adult library

- In Whisparr, use `/adult` as the root folder so imports never land under `/movies` or `/tv`
- In Jellyfin, create a separate library named `Adult` pointing at `/adult`
- Then set selective access per user in **Dashboard → Users → Library access** so only approved accounts can see the `Adult` library

### Stash + Stasharr Portal

Bootstrap the adult request stack with one command:

```bash
make setup-stasharr
```

That target will:
- create any missing Stash / Stasharr directories under `CONFIG_ROOT`
- auto-generate missing local-only Stasharr secrets in `.env`
- enable the `stasharr` compose profile so future `make up/down` includes it
- start **Stash** on `http://NAS_IP:9998` (host 9998 → container 9999 to avoid Dozzle's 9999)
- start **Stasharr Portal** on `http://NAS_IP:3000`
- read Whisparr's live API key, ensure the `/adult` root folder exists, and wire **StashDB** + **Stash** + **Whisparr** in Stasharr
- queue the initial Stash scan of `/adult`

If the target had to generate a Stasharr admin password, it prints it once and saves it in your local `.env` so the login survives future pulls.

### Jellyseerr

Point at Docker host gateway for Sonarr/Radarr URLs:
- Radarr: `http://172.17.0.1:7878`
- Sonarr: `http://172.17.0.1:8989`

Disable "Tag Requests" in Jellyseerr's Radarr settings if requests aren't arriving.

### Bazarr

Bazarr is exposed on LAN at `http://NAS_IP:6767` by default (or whatever you set for `BAZARR_PORT` in `.env`).

Bootstrap it with:

```bash
make setup-bazarr
```

That target will:
- start `gluetun`, `sonarr`, `radarr`, and `bazarr`
- wire Bazarr to Sonarr/Radarr using the live API keys from their config files
- create or update a default `English + Spanish` language profile
- make that profile the default for new series and movies
- enable `embeddedsubtitles` and `podnapisi` by default as a no-credential baseline

For better coverage, especially if you want more English + Spanish results, also add **OpenSubtitles.com**. You can either:
- enter it manually in the Bazarr UI, or
- set `BAZARR_OPENSUBTITLESCOM_USERNAME` and `BAZARR_OPENSUBTITLESCOM_PASSWORD` in `.env` before `make setup-bazarr`

Recommended provider stack for this setup:
- `embeddedsubtitles` for subtitles already bundled inside files
- `podnapisi` as a free no-login provider
- `opensubtitlescom` for broader coverage once you add an account

Important: Bazarr manages **subtitles only**. It does **not** download or swap audio tracks/dubs. It can use detected audio-language metadata to influence subtitle rules, but it does not change the audio stream itself.

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

One-shot setup / repair:
```bash
make setup-recyclarr
```

That target:
- reads the live API keys from `CONFIG_ROOT/sonarr/config.xml` and `CONFIG_ROOT/radarr/config.xml`
- renders the repo template to `CONFIG_ROOT/recyclarr/recyclarr.yml`
- ensures the `recyclarr` container is running
- runs `recyclarr state repair --adopt` so existing Sonarr/Radarr profiles can be adopted instead of colliding by name
- runs `recyclarr sync` to apply the official TRaSH guide profiles

Preview adoption + sync without changing Sonarr/Radarr:
```bash
make recyclarr-preview
```

If you only want to refresh the rendered config and leave the actual sync for later:
```bash
make sync-recyclarr
```

The repo now uses official TRaSH quality profile IDs (`trash_id`) plus `custom_format_groups`, instead of hand-maintained quality ladders. Sonarr/Radarr are reached via `http://gluetun:8989` / `http://gluetun:7878`.

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
