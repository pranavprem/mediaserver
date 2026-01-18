# UGREEN NAS Media Server (Docker Compose) — Rebuild Guide

This repository is the "single-folder" record of the media server stack that was built on a UGREEN NAS. The Docker Compose project lives at `/volume1/docker/mediaserver`, while persistent data (configs, downloads, movies, tv) lives under `/volume1/media`.

The intent: clone this repo onto a fresh NAS, follow the steps in order, and end up with the same working setup (including fixes for the exact problems that happened during the original build).

---

## What this stack does

- Routes **download traffic** through ProtonVPN using `gluetun` + WireGuard.
- Uses both **torrents** (qBittorrent) and **Usenet** (SABnzbd + Newshosting + NZBGeek).
- Automates TV + Movies with Sonarr/Radarr, with indexers managed by Prowlarr.
- Provides a request UI with Jellyseerr that can drive Sonarr/Radarr and integrate with media servers.
- Streams locally via Jellyfin; Plex can be added for devices that require it.

---

## Service map (mental model)

**Download path:**
- Indexers configured in Prowlarr → synced to Sonarr/Radarr (indexers only).
- Requests in Jellyseerr → Sonarr/Radarr → download client (qBit or SAB) → `/downloads` → import/move into `/tv` and `/movies` → Jellyfin library scan.

**Networking rules learned the hard way:**
- Any container using `network_mode: "service:gluetun"` **cannot publish its own ports**; ports must be exposed via the gluetun service.
- SABnzbd listens on internal port **8080** (normal) even if the NAS exposes it on another port (example: 8383).

---

## Repo expectations (what should exist)

**In this repo (committed):**
- `docker-compose.yaml`
- `.env.example` (template only, no secrets)
- `README.md` (this file)

**On the NAS (NOT committed):**
- `/volume1/media/config/*` (service databases, tokens, settings)
- `/volume1/media/downloads/*`
- `/volume1/media/movies/*`
- `/volume1/media/tv/*`
- `.env` (real secrets)

---

## Prereqs

- UGREEN OS with Docker + Docker Compose available.
- ProtonVPN account with WireGuard credentials for gluetun.
- Newshosting account and NZBGeek API key (Usenet pipeline used here).
- Optional: domain for future remote access work.

---

## Step 0 — Decide your paths and ports

This guide assumes:
- Compose project folder: `/volume1/docker/mediaserver`
- Persistent data root: `/volume1/media`
- A non-8080 external port for SABnzbd UI (example: 8383) because 8080 is intentionally avoided.

---

## Step 1 — Create folders (fresh NAS)

Create the repo folder and the persistent folder structure:

```bash
mkdir -p /volume1/docker/mediaserver
mkdir -p /volume1/media/{downloads,downloads/incomplete,movies,tv}
mkdir -p /volume1/media/config/{gluetun,qbittorrent,sabnzbd,prowlarr,sonarr,radarr,jellyfin,jellyseerr,plex}
```

---

## Step 2 — Fix permissions (this caused the most pain)

If permissions are wrong, you'll see issues like Jellyfin failing to start, *arr apps failing to import, or services not being able to write configs.

### Determine your UID/GID

On the NAS:

```bash
id
```

During this build, the working values were:
- UID (PUID): 1000
- GID (PGID): 100

(If yours differ, use your real values everywhere below.)

### Apply ownership

```bash
chown -R 1000:100 /volume1/media
```

### Verify

```bash
ls -ld /volume1/media /volume1/media/config /volume1/media/downloads
```

---

## Step 3 — Create .env and .env.example

You want two files:
- `.env` (real secrets) — never commit
- `.env.example` (template) — commit

**Minimum .env.example shape:**

```bash
TZ=America/Los_Angeles
PUID=1000
PGID=100

CONFIG_ROOT=/volume1/media/config
DOWNLOADS_ROOT=/volume1/media/downloads
MOVIES_ROOT=/volume1/media/movies
TV_ROOT=/volume1/media/tv

QBITTORRENT_TORRENT_PORT=6881
QBITTORRENT_PORT=8888
PROWLARR_PORT=9696
RADARR_PORT=7878
SONARR_PORT=8989
SABNZBD_PORT=8080
JELLYFIN_PORT=8096
JELLYSEERR_PORT=5055

# Proton WireGuard (fill in real values in .env)
WIREGUARD_PRIVATE_KEY=REDACTED
WIREGUARD_ADDRESSES=REDACTED/32

# Optional: Plex claim token
PLEX_CLAIM=REDACTED
```

**Notes:**
- SABnzbd's internal web UI port is 8080; you only change the external/LAN port.
- Avoiding external port 8080 was intentional in this setup.

---

## Step 4 — Deploy

From the repo folder:

```bash
cd /volume1/docker/mediaserver
docker compose up -d
docker compose ps
```

**Logs when something won't start:**

```bash
docker compose logs -f --tail=200
```

---

## Step 5 — First-run configuration checklist

### qBittorrent: stop the random password resets

**Symptom:** qBit generates a new temporary password on restart.

**Fix:**
1. Grab temp password:
   ```bash
   docker logs qbittorrent 2>&1 | grep -i "temporary password" -n
   ```
2. Log into qBit WebUI (example): `http://NAS_IP:8888`
3. Set a permanent password: **Tools → Options → Web UI → set username/password**.

### SABnzbd: internal vs external port (critical)

**Facts:**
- SABnzbd listens on internal port 8080 (expected).
- You access it from LAN via `http://NAS_IP:${SABNZBD_PORT}` (example: 8383).

**If SAB UI doesn't load on the NAS port:**
- This stack used `network_mode: "service:gluetun"` for SABnzbd, so SAB cannot publish ports itself.
- The working fix was to publish SAB's UI via gluetun as `host-port:8080`.

### Prowlarr: what it syncs (and what it doesn't)

Prowlarr syncs indexers to Sonarr/Radarr, but not download clients.

**So you must:**
- Add NZBGeek + any torrent indexers in Prowlarr.
- Add qBittorrent and SABnzbd as download clients in Sonarr/Radarr manually.

### Remote Path Mappings (Usenet import failures)

**Symptom:** Radarr/Sonarr complains that SAB is downloading into a path that doesn't exist in the container.

**Fix used:**

SABnzbd folders:
- Temporary: `/incomplete-downloads`
- Completed: `/downloads`

**Radarr/Sonarr → Settings → Download Clients → Remote Path Mappings:**
- Host: `172.17.0.1`
- Remote Path: `/downloads`
- Local Path: `/downloads`

### Jellyseerr → Radarr "Test OK but requests never arrive"

**Symptom:** Jellyseerr connectivity test passes, but movie requests never show up in Radarr (Sonarr works).

**Cause observed:** Radarr rejects Jellyseerr's attempt to auto-create request tags (400 error).

**Fix used:**
- **Jellyseerr → Settings → Radarr → Edit:** Disable "Tag Requests", or use a simple tag without invalid characters/spaces.
- If needed: remove problematic tags in Radarr.

### Jellyseerr can't resolve radarr / container DNS issues

**Symptom:** `docker exec jellyseerr ping radarr` → bad address.

In this setup, the practical workaround that immediately worked was to point Jellyseerr at the Docker host gateway IP (`172.17.0.1`) instead of relying on container DNS.

**Example URLs in Jellyseerr:**
- Radarr: `http://172.17.0.1:7878`
- Sonarr: `http://172.17.0.1:8989`

---

## Verification checklist (trust but verify)

### VPN routing is real

Check qBittorrent's external IP:

```bash
docker exec qbittorrent curl ifconfig.me
```

**Expected:** a ProtonVPN exit IP, not your ISP IP.

### Imports are working

Completed downloads should be imported/moved from `/volume1/media/downloads` into:
- `/volume1/media/tv/...` for Sonarr
- `/volume1/media/movies/...` for Radarr

### Jellyfin sees content

If Jellyfin shows "No valid media source", it often meant the media hadn't completed importing yet.

---

## Maintenance commands

**Update containers:**
```bash
docker compose pull && docker compose up -d
```

**Status:**
```bash
docker compose ps
```

**Logs:**
```bash
docker compose logs --tail=200
```

---

## Notes / next steps

Remote access planning was discussed (reverse proxy / Cloudflare tunnel), but this repo focuses on the local LAN stack first.

Plex can be added later for device compatibility; Jellyseerr can integrate with both Jellyfin and Plex.
