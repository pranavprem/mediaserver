# Very NAS Media Server

I got a NAS and then decided to use it as a media server. In the process, I ended up orchestrating a rather cool stack of docker containers. So here it is. I'm told it's "Very NAS"

---- The readme beyond this point is written by AI ----

The intent: clone this repo onto a fresh NAS, follow the steps in order, and end up with the same working setup (including fixes for the exact problems that happened during the original build).

---

## What this stack does

- Routes **download traffic** through ProtonVPN using `gluetun` + WireGuard.
- Uses both **torrents** (qBittorrent) and **Usenet** (SABnzbd + Newshosting + NZBGeek).
- Automates TV + Movies with Sonarr/Radarr, with indexers managed by Prowlarr.
- **Recyclarr** auto-syncs quality profiles from TRaSH guides.
- Provides a request UI with Jellyseerr that can drive Sonarr/Radarr and integrate with media servers.
- Streams locally via Jellyfin; Plex can be added for devices that require it.
- Self-hosted password manager (Vaultwarden) via Cloudflare tunnel.
- Self-hosted photos (Immich) with ML-powered face recognition and smart search.
- **Portainer** for container management UI.
- **Watchtower** for automatic container updates.

---

## Architecture

### Network Isolation

Services are isolated into purpose-specific networks:

| Network | Purpose | Containers |
|---------|---------|------------|
| `downloads` | VPN-tunneled traffic | gluetun, qbittorrent, sabnzbd, prowlarr, radarr, sonarr |
| `media` | Media streaming & management | jellyfin, jellyseerr, plex, recyclarr |
| `proxy` | Cloudflare tunnel access | cloudflared, jellyfin, jellyseerr, plex, vaultwarden, immich-server |
| `immich` | Photo stack (internal) | immich-*, postgres, redis |
| `management` | Container management | portainer, watchtower |

### Security Features

- ✅ All containers have `security_opt: no-new-privileges`
- ✅ All containers have health checks
- ✅ VPN kill switch (gluetun firewall)
- ✅ Immich database isolated from other services
- ✅ Docker socket mounted read-only where needed
- ✅ Services depend on healthy upstream containers

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
- `example.env` (template only, no secrets)
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
mkdir -p /volume1/media/{downloads,downloads/incomplete,movies,tv,photos}
mkdir -p /volume1/media/config/{gluetun,qbittorrent,sabnzbd,prowlarr,sonarr,radarr,jellyfin,jellyseerr,plex,vaultwarden,portainer,recyclarr}
mkdir -p /volume1/media/config/immich/{postgres,redis,model-cache}
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

Copy `example.env` to `.env` and fill in your values:

```bash
cp example.env .env
nano .env
```

### Generate secure passwords

```bash
# For Immich database
openssl rand -base64 32

# For Immich Redis  
openssl rand -base64 32

# For Vaultwarden admin token
docker run --rm -it vaultwarden/server /vaultwarden hash
```

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

### Health checks

All containers should show "healthy":

```bash
docker compose ps
```

---

## Maintenance commands

**Update containers (manual):**
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

**Watchtower will auto-update containers** at 4 AM daily (configurable via `WATCHTOWER_SCHEDULE`).

---

## Recyclarr (TRaSH guides sync)

Recyclarr automatically syncs quality profiles from the TRaSH guides to your Sonarr/Radarr instances.

### First-time setup

1. Generate config template:
   ```bash
   docker exec recyclarr recyclarr config create
   ```

2. Edit the config:
   ```bash
   nano /volume1/media/config/recyclarr/recyclarr.yml
   ```

3. Add your Sonarr/Radarr API keys and URLs. Example:
   ```yaml
   sonarr:
     main:
       base_url: http://172.17.0.1:8989
       api_key: your-sonarr-api-key
       quality_definition:
         type: series
       quality_profiles:
         - name: WEB-1080p
   
   radarr:
     main:
       base_url: http://172.17.0.1:7878
       api_key: your-radarr-api-key
       quality_definition:
         type: movie
       quality_profiles:
         - name: HD Bluray + WEB
   ```

4. Test sync:
   ```bash
   docker exec recyclarr recyclarr sync
   ```

5. Set up scheduled sync (add to crontab or use the container's built-in scheduler):
   ```bash
   docker exec recyclarr recyclarr sync --config /config/recyclarr.yml
   ```

---

## Portainer

Portainer provides a web UI for managing your Docker containers.

**Access:** `http://NAS_IP:9000`

**First-time setup:**
1. Open Portainer in browser
2. Create admin account
3. Select "Docker" as the environment
4. Connect to local Docker socket

**Features:**
- View container logs
- Start/stop/restart containers
- View resource usage
- Manage volumes and networks

---

## Gitea (self-hosted Git)

Gitea provides a lightweight self-hosted Git server — useful for private repos, backups, and agent memory storage.

**Access:** `http://10.0.0.116:41234` (LAN only, not exposed to internet)

### First-time setup

1. Create config folder:
   ```bash
   mkdir -p /volume1/media/config/gitea
   chown -R 1000:100 /volume1/media/config/gitea
   ```

2. Add to `.env`:
   ```bash
   NAS_IP=10.0.0.116
   GITEA_PORT=41234
   GITEA_DISABLE_REGISTRATION=false  # temporarily for setup
   ```

3. Deploy:
   ```bash
   docker compose up -d gitea
   ```

4. Access `http://10.0.0.116:41234` and create your admin account

5. **After setup:** Set `GITEA_DISABLE_REGISTRATION=true` and redeploy

### Pushing to Gitea

From any machine on the LAN:
```bash
git remote add nas http://10.0.0.116:41234/username/repo.git
git push nas main
```

### Neo's memory backup

Neo backs up his SQLite memory database here for durability:
```bash
cd ~/.openclaw
git init
git add neo-memory.db
git commit -m "Memory backup"
git remote add nas http://10.0.0.116:41234/pranav/neo-memory.git
git push -u nas main
```

---

## Vaultwarden (password manager)

Vaultwarden is accessible via the Cloudflare tunnel at **vault.pranavprem.com**.

**Cloudflare tunnel route:** Use `http://vaultwarden:7777` (not https). Vaultwarden serves HTTP; TLS is terminated at Cloudflare's edge. Traffic between cloudflared and vaultwarden stays on the local Docker network.

**First-time setup:**
1. Add `VAULTWARDEN_DOMAIN` and `VAULTWARDEN_ADMIN_TOKEN` to `.env`. Generate admin token: `docker run --rm -it vaultwarden/server /vaultwarden hash`
2. Set `VAULTWARDEN_SIGNUPS_ALLOWED=true` in `.env` to create your account.
3. Create account at https://vault.pranavprem.com, then set `VAULTWARDEN_SIGNUPS_ALLOWED=false` and redeploy.
4. Enable 2FA (TOTP or WebAuthn) in your vault settings.
5. **Recommended:** Set `VAULTWARDEN_ADMIN_TOKEN=` (empty) to disable admin panel after setup.

---

## Immich (self-hosted photos)

Immich is accessible via the Cloudflare tunnel at **photos.pranavprem.com** (configure in Cloudflare dashboard).

### Architecture

Immich runs in an isolated network (`immich`) with:
- **PostgreSQL** (with pgvector for ML embeddings)
- **Redis** (for job queue)
- **Machine Learning** container (face recognition, smart search)
- **Server** (API + web interface)

Only `immich-server` is on the proxy network (for Cloudflare tunnel access). Database and Redis are isolated.

### First-time setup

1. Folders should already exist from Step 1. Verify:
   ```bash
   ls -la /volume1/media/config/immich/
   ls -la /volume1/media/photos/
   ```

2. Generate strong passwords and add to `.env`:
   ```bash
   # Generate passwords
   openssl rand -base64 32  # for IMMICH_DB_PASSWORD
   openssl rand -base64 32  # for IMMICH_REDIS_PASSWORD
   ```

3. Configure Cloudflare tunnel:
   - Add route for `photos.pranavprem.com` → `http://immich-server:2283`

4. Deploy (databases first to initialize):
   ```bash
   docker compose up -d immich-postgres immich-redis
   sleep 15  # let DB initialize
   docker compose up -d immich-machine-learning immich-server
   ```

5. Create your admin account at https://photos.pranavprem.com

### Mobile app setup

Download Immich app (iOS/Android), use `https://photos.pranavprem.com` as the server URL.

### Backup strategy

Back up the PostgreSQL data regularly:
```bash
docker exec immich-postgres pg_dump -U postgres immich > immich_backup_$(date +%Y%m%d).sql
```

---

## Watchtower (auto-updates)

Watchtower automatically updates your containers when new images are available.

**Default schedule:** 4 AM daily

**Configuration:**
- `WATCHTOWER_SCHEDULE` — Cron expression for update checks
- `WATCHTOWER_NOTIFICATIONS` — Enable notifications (shoutrrr format)
- `WATCHTOWER_NOTIFICATION_URL` — Notification destination

**Notification examples:**
```bash
# Discord webhook
WATCHTOWER_NOTIFICATIONS=shoutrrr
WATCHTOWER_NOTIFICATION_URL=discord://token@webhookid

# Telegram
WATCHTOWER_NOTIFICATION_URL=telegram://token@telegram?chats=chat-id
```

**Manual update check:**
```bash
docker exec watchtower /watchtower --run-once
```

**Exclude containers from auto-update:**
Add label to the container:
```yaml
labels:
  - "com.centurylinklabs.watchtower.enable=false"
```

---

## Notes / next steps

Remote access planning was discussed (reverse proxy / Cloudflare tunnel), but this repo focuses on the local LAN stack first.

Plex can be added later for device compatibility; Jellyseerr can integrate with both Jellyfin and Plex.
