# CLAUDE.md

## Project Overview
This is Pranav's self-hosted media server stack running on a UGREEN NAS. It uses Docker Compose to orchestrate all services. The NAS deployment tracks GitHub `master`.

## Architecture
- **VPN:** Gluetun (all download clients route through VPN via `network_mode: service:gluetun`)
- **Download Clients:** qBittorrent + SABnzbd (behind Gluetun)
- **Arr Stack:** Sonarr, Radarr, Prowlarr, Bazarr (media automation)
- **Media Servers:** Jellyfin + Plex
- **Request UI:** Seerr (drives Sonarr/Radarr; Docker service/container name remains `jellyseerr` for compatibility)
- **Photos:** Immich (Google Photos replacement)
- **Management:** Portainer is now a separate bootstrap compose stack (HTTP only, port 9443 removed — conflicts with NAS); Watchtower auto-updates every container on the host except gluetun
- **Monitoring:** Dozzle (:9999), Prometheus (:9090), Grafana (:3333), cAdvisor, node-exporter on `monitoring` network
- **Git:** GitHub `master` for deployment; Gitea remains a Git service in the stack (:41234)
- **Security:** Vaultwarden (tunnel-only, signups disabled), Cloudflare Tunnel for external access
- **Other:** Recyclarr (TRaSH quality profiles — still needs proper setup)

## Repo Structure
```
docker-compose.yaml   # Full stack definition (~27KB, ~600 lines), project name pinned to mediaserver
portainer-compose.yaml # Standalone Portainer bootstrap stack
.env                  # Secrets (NOT committed, copy from example.env)
example.env           # Template with all variables
Makefile              # Operational targets (sync configs, update gluetun)
prometheus.yml        # Prometheus scrape config (synced to NAS via make)
recyclarr.yml         # TRaSH quality profiles (synced to NAS via make)
grafana/
  dashboards/         # mediaserver.json
  provisioning/       # Auto-provisioning for Grafana datasources + dashboards
README.md             # Comprehensive setup guide
CLAUDE.md             # This file
```

## Remotes
- **github (deployment source):** `https://github.com/pranavprem/mediaserver.git`
- **origin (stale Gitea mirror):** LAN Gitea — URL in `CLAUDE.local.md`
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
make update-seerr      # Backup Jellyseerr config, fix ownership, pull Seerr, recreate request UI
make update-gluetun    # Safe gluetun update: pull → stop dependents → recreate → wait healthy → restart dependents
```

The Makefile reads `CONFIG_ROOT` from `.env` (via `include .env`). Prometheus is copied from repo to `$CONFIG_ROOT/prometheus/`. Recyclarr is rendered from the repo template plus live API keys read from `$CONFIG_ROOT/{sonarr,radarr}/config.xml`.

## Network Architecture (isolated by function)
| Network | Purpose | Key containers |
|---------|---------|----------------|
| `downloads` | VPN-tunneled traffic | gluetun, qbittorrent, sabnzbd, prowlarr, radarr, sonarr, bazarr, recyclarr |
| `media` | Media streaming | jellyfin, jellyseerr (Seerr), plex, recyclarr |
| `proxy` | Cloudflare tunnel → media servers | cloudflared, jellyfin, jellyseerr (Seerr), plex |
| `proxy-vault` / `proxy-photos` / `proxy-docs` / `proxy-git` | Cloudflare tunnel → one sensitive backend each | cloudflared + vaultwarden / immich-server / paperless-webserver / gitea |
| `paperless` | Document stack (isolated DB/Redis) | paperless-webserver, paperless-ai, paperless-ai-2, paperless-postgres, paperless-redis, paperless-gotenberg, paperless-tika |
| `socket-proxy` | Read-only Docker API for Dozzle (internal, no route out) | docker-socket-proxy, dozzle |
| `immich` | Photo stack (isolated DB/Redis) | immich-server, immich-ml, immich-postgres, immich-redis |
| `management` | Git + auto-updates | watchtower, gitea |
| `monitoring` | Observability | prometheus, grafana, cadvisor, node-exporter, dozzle |

## Key Configuration Notes
- **Gluetun dependents** (qbittorrent, sabnzbd, prowlarr, radarr, sonarr, bazarr) use `network_mode: service:gluetun` — they share gluetun's network namespace and CANNOT publish their own ports
- Watchtower: updates everything on the host except gluetun (labelled `watchtower.enable=false`) and the names in `WATCHTOWER_DISABLE_CONTAINERS` (stack env; for locally built images, kept out of the repo). Rolling restarts DISABLED (was causing restart spam)
- No extra login layer (no Cloudflare Access / forward-auth) in front of the tunneled apps: each app's own login is the gate, because the phone apps cannot pass one. Prompt updates and the per-backend networks are what compensate
- Deployment is Portainer-only: stack env lives in Portainer, nothing needs pulling on the NAS. The NAS checkout and `.env` matter only for `make` targets
- Tunneled backends each get their own `proxy-*` network so a compromised media server cannot reach Vaultwarden or Paperless at all (Immich and Gitea still publish LAN ports, reachable through the host). A new tunneled service needs its own network added to `cloudflared`
- `docker.sock:ro` does NOT make the Docker API read-only. Dozzle goes through `docker-socket-proxy` (blocks writes, but container env is still readable through it); only Watchtower, cAdvisor and the proxy touch the socket
- Secrets fail closed: required passwords use `${VAR:?}` so a missing value stops the deploy instead of falling back to a default
- Portainer: standalone bootstrap stack using `${CONFIG_ROOT}/portainer`; healthcheck disabled (no tools in container), port 9443 removed (conflicts with NAS)
- Portainer should not be part of the stack it manages. Use `make portainer-up` once, then import `mediaserver` as a Git-backed stack named `mediaserver`.
- qBit: password persistence was an issue (fixed 2026-03-03) — must set password via WebUI on first run
- Immich: ML networking fixed by removing `internal: true` from immich network. Face detection + facial recognition running. Use the Immich-maintained Postgres image with VectorChord/pgvector; Watchtower updates the server and ML images; the Postgres image is pinned, so bump its tag to match the release's compose file when Immich asks for a newer one.
- Cloudflare Tunnel routes: vault.yourdomain.com, photos.yourdomain.com, jellyfin, etc.
- Vaultwarden: signups disabled, tunnel-only access (no LAN port exposed), HTTP internally (TLS at Cloudflare edge)
- Prometheus: runs as user `nobody` — config files must be `chmod 644`
- Grafana: dashboards + provisioning files must be world-readable (`chmod 755` dirs, `chmod 644` files)
- Recyclarr uses official TRaSH guide templates (`trash_id` quality profiles + `custom_format_groups`), and `make setup-recyclarr` auto-renders live API keys, adopts existing Arr state with `recyclarr state repair --adopt`, then syncs
- Recyclarr reaches Arr services via `http://gluetun:<port>` because Sonarr/Radarr share gluetun's network namespace
- Bazarr is bootstrapped by `scripts/setup_bazarr.py` plus `make setup-bazarr`, which wires live Sonarr/Radarr API keys, seeds a default English + Spanish subtitle profile, and enables `embeddedsubtitles` + `podnapisi` by default

## Cross-Compose Monitoring
Other Docker Compose projects can be scraped by connecting their container to the `mediaserver_monitoring` network:
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
- Gluetun recreation orphans all `network_mode: service:gluetun` containers — never let Watchtower update it
- Portainer "Pull and redeploy" force-recreates EVERY container in the stack, gluetun included, even when nothing changed. Portainer's automatic Git update re-pulls EVERY image on each change to `master`. After either, containers from other compose projects that share gluetun must be recreated
- Immich ML needs explicit DNS config (`8.8.8.8`, `1.1.1.1`) to download models from huggingface.co
- Prometheus config must be world-readable or it silently fails

## Environment
- **Host:** UGREEN NAS (address in `CLAUDE.local.md`)
- **Orchestration:** Docker Compose
- **External access:** Cloudflare Tunnel
- **LAN access:** Services available on `<NAS_IP>:<port>`
- **VPN:** ProtonVPN (WireGuard, Switzerland servers)

## Public Repo Hygiene
- `master` is public. Private context (real domain, addresses, household names, other projects, pending security work) lives in gitignored `CLAUDE.local.md` and `docs/private/` — never in tracked files or commit messages.
- Run `make leak-scan` before every push; it scans each unpushed commit against the gitignored `.leak-terms` list and fails closed if the list is missing.

## Owner
Pranav Prem
