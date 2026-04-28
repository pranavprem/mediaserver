# CLAUDE.md

## Project Overview
This is Pranav's self-hosted media server stack running on a UGREEN NAS at 10.0.0.116. It uses Docker Compose to orchestrate all services. The repo lives on the NAS and is mirrored to GitHub.

## Architecture
- **VPN:** Gluetun (all download clients route through VPN via `network_mode: service:gluetun`)
- **Download Clients:** qBittorrent + SABnzbd (behind Gluetun)
- **Arr Stack:** Sonarr, Radarr, Prowlarr, Bazarr (media automation)
- **Media Servers:** Jellyfin + Plex
- **Request UI:** Jellyseerr (drives Sonarr/Radarr)
- **Photos:** Immich (Google Photos replacement) — 29,170 assets (206.3GB) migrated from Google Photos via immich-go
- **Management:** Portainer (HTTP only, port 9443 removed — conflicts with NAS), Watchtower (auto-updates)
- **Monitoring:** Dozzle (:9999), Prometheus (:9090), Grafana (:3333), cAdvisor, node-exporter on `monitoring` network
- **Git:** Gitea (LAN-only, :41234)
- **Security:** Vaultwarden (tunnel-only, signups disabled), Cloudflare Tunnel for external access
- **Other:** Recyclarr (TRaSH quality profiles — still needs proper setup)

## Repo Structure
```
docker-compose.yaml   # Full stack definition (~27KB, ~600 lines)
.env                  # Secrets (NOT committed, copy from example.env)
example.env           # Template with all variables
Makefile              # Operational targets (sync configs, update gluetun)
prometheus.yml        # Prometheus scrape config (synced to NAS via make)
recyclarr.yml         # TRaSH quality profiles (synced to NAS via make)
grafana/
  dashboards/         # mediaserver.json, oracle.json
  provisioning/       # Auto-provisioning for Grafana datasources + dashboards
README.md             # Comprehensive setup guide
CLAUDE.md             # This file
```

## Remotes
- **origin (Gitea, primary):** `http://10.0.0.116:41234/pranav-gitea/mediaserver.git`
- **github:** `https://github.com/pranavprem/mediaserver.git`
- **Branch:** `master`

## Key Operational Commands
```bash
make sync-configs      # Sync prometheus.yml + render recyclarr.yml into CONFIG_ROOT, refresh services
make sync-prometheus   # Sync just prometheus config
make sync-recyclarr    # Render recyclarr.yml with live Arr API keys, ensure Recyclarr is running
make recyclarr-preview # Preview Recyclarr adoption + sync without changing Sonarr/Radarr
make setup-recyclarr   # One-shot Recyclarr setup, adopt existing Arr state, and sync TRaSH profiles
make setup-bazarr      # Start Bazarr, wire Sonarr/Radarr, and seed default English+Spanish subtitles
make sync-grafana      # Restart Grafana to pick up dashboard changes
make update-gluetun    # Safe gluetun update: pull → stop dependents → recreate → wait healthy → restart dependents
```

The Makefile reads `CONFIG_ROOT` from `.env` (via `include .env`). Prometheus is copied from repo to `$CONFIG_ROOT/prometheus/`. Recyclarr is rendered from the repo template plus live API keys read from `$CONFIG_ROOT/{sonarr,radarr}/config.xml`.

## Network Architecture (6 isolated networks)
| Network | Purpose | Key containers |
|---------|---------|----------------|
| `downloads` | VPN-tunneled traffic | gluetun, qbittorrent, sabnzbd, prowlarr, radarr, sonarr, bazarr, recyclarr |
| `media` | Media streaming | jellyfin, jellyseerr, plex, recyclarr |
| `proxy` | Cloudflare tunnel | cloudflared, jellyfin, jellyseerr, plex, vaultwarden, immich-server |
| `immich` | Photo stack (isolated DB/Redis) | immich-server, immich-ml, immich-postgres, immich-redis |
| `management` | Container management | portainer, watchtower, gitea |
| `monitoring` | Observability | prometheus, grafana, cadvisor, node-exporter, dozzle |

## Key Configuration Notes
- **Gluetun dependents** (qbittorrent, sabnzbd, prowlarr, radarr, sonarr, bazarr) use `network_mode: service:gluetun` — they share gluetun's network namespace and CANNOT publish their own ports
- Prowlarr indexer priorities: NZBgeek=1, DrunkenSlug=5, torrents=25
- Watchtower: gluetun excluded (`watchtower.enable=false`), rolling restarts DISABLED (was causing restart spam)
- Portainer: healthcheck disabled (no tools in container), port 9443 removed (conflicts with NAS)
- qBit: password persistence was an issue (fixed 2026-03-03) — must set password via WebUI on first run
- Immich: ML networking fixed by removing `internal: true` from immich network. Face detection + facial recognition running.
- Abhinaya has her own Immich account
- Cloudflare Tunnel routes: vault.pranavprem.com, photos.pranavprem.com, jellyfin, etc.
- Vaultwarden: signups disabled, tunnel-only access (no LAN port exposed), HTTP internally (TLS at Cloudflare edge)
- Prometheus: runs as user `nobody` — config files must be `chmod 644`
- Grafana: dashboards + provisioning files must be world-readable (`chmod 755` dirs, `chmod 644` files)
- Recyclarr uses official TRaSH guide templates (`trash_id` quality profiles + `custom_format_groups`), and `make setup-recyclarr` auto-renders live API keys, adopts existing Arr state with `recyclarr state repair --adopt`, then syncs
- Recyclarr reaches Arr services via `http://gluetun:<port>` because Sonarr/Radarr share gluetun's network namespace
- Bazarr is bootstrapped by `scripts/setup_bazarr.py` plus `make setup-bazarr`, which wires live Sonarr/Radarr API keys and seeds a default English + Spanish subtitle profile

## Cross-Compose Monitoring
Other Docker Compose projects (e.g., Oracle trading system) can be scraped by connecting their container to the `mediaserver_monitoring` network:
```bash
docker network connect mediaserver_monitoring <container_name>
```
Then add a scrape job to `prometheus.yml`.

## Pending Work
- [ ] Verify live Recyclarr sync on the NAS after the next `make setup-recyclarr` run
- [ ] Set up Grafana dashboards properly (provisioning is in place, dashboards need tuning)
- [ ] Verify current state of arr services on gluetun network (was reverted at one point)

## Important Lessons (Hard-Won)
- `sudo apt update && apt install` on UGREEN NAS **broke Docker app** — NEVER run apt on the NAS. Reinstall Docker app to fix.
- Watchtower rolling restarts caused restart spam — disabled
- Gluetun recreation orphans all `network_mode: service:gluetun` containers — always use `make update-gluetun`
- Immich ML needs explicit DNS config (`8.8.8.8`, `1.1.1.1`) to download models from huggingface.co
- Prometheus config must be world-readable or it silently fails

## Environment
- **Host:** UGREEN NAS (10.0.0.116)
- **Orchestration:** Docker Compose
- **External access:** Cloudflare Tunnel
- **LAN access:** All services available on 10.0.0.116:<port>
- **VPN:** ProtonVPN (WireGuard, Switzerland servers)

## Owner
Pranav Prem (pranavprem93@gmail.com)
