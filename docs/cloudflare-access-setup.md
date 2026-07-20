# Cloudflare Access Setup — H1 Fix

Step-by-step checklist for gating the tunneled services behind Cloudflare Access
(Zero Trust). All work happens in the Cloudflare dashboard — nothing in this repo
changes. Budget ~15 minutes.

**End state:**

| Hostname | Treatment | Why |
|---|---|---|
| `photos.yourdomain.com` (Immich) | **Full Access** — identity login for browsers, service token for phone apps | Apps support custom headers, so full gating costs nothing |
| `vault.yourdomain.com` (Vaultwarden) | **Access on web vault + `/admin`**, bypass on client API paths | Bitwarden clients can't pass Access; API stays on master-password auth + rate limit |
| `paperless.yourdomain.com` | **Access on web UI**, bypass on `/api/*` | Mobile app uses API tokens and can't pass Access |
| `jellyfin.yourdomain.com` | **No change** (app auth only) | Decision 2026-07-12: Jellyfin apps used remotely; they can't pass Access. Keep it auto-updating in Watchtower. |
| `git.yourdomain.com` (Gitea) | **No change** (app auth only) | Decision 2026-07-12: keep as-is. Audit recommendation to remove the route stands if this is ever revisited. Registration stays disabled. |

---

## Step 0 — Prerequisites

1. Go to [one.dash.cloudflare.com](https://one.dash.cloudflare.com) → pick the
   account that owns `yourdomain.com`. If Zero Trust isn't set up yet, choose a
   team name (e.g. `pranavprem`) and the **Free plan** (50 users included).
2. **Settings → Authentication → Login methods**: make sure **One-time PIN** is
   enabled (it is by default). Optionally add **Google** as a login method for
   one-click logins.

> Heads-up: as of 2026-07-12 all five hostnames returned HTTP 530 (tunnel error)
> — the tunnel itself was down or unhealthy. Check `docker ps` / Dozzle for the
> `cloudflared` container on the NAS before testing anything below, or every
> verification step will fail with 530 regardless of Access config.

## Step 1 — Create the "household" Access group

Membership lives in ONE place; every policy references the group, so adding a
person later is a single edit.

1. **Access → Access groups → Add a group**
2. Name: `household`
3. Include → **Emails**: `pranavprem93@gmail.com`, `<abhinaya's email>`
4. Save. (To add someone later: edit this group, nothing else.)

## Step 2 — Immich: full Access + service token for the apps

### 2a. Service token (lets the phone apps through the gate)

1. **Access → Service auth → Service tokens → Create service token**
2. Name: `immich-mobile`, duration: 1 year (set a calendar reminder to rotate).
3. **Copy the Client ID and Client Secret now** — the secret is shown once.

### 2b. Access application

1. **Access → Applications → Add an application → Self-hosted**
2. Name: `Immich`, session duration: 1 month.
3. Public hostname: `photos.yourdomain.com` (no path — protects everything).
4. Policies (two):
   - `allow-household` — Action **Allow**; Include → Access group → `household`.
   - `immich-apps` — Action **Service Auth**; Include → Service token → `immich-mobile`.
5. Save.

### 2c. Point the phone apps at the token (both phones: yours + Abhinaya's)

In the Immich app: **Settings → Advanced → Custom proxy headers**, add:

| Header | Value |
|---|---|
| `CF-Access-Client-Id` | `<client id>.access` |
| `CF-Access-Client-Secret` | `<client secret>` |

Then log out/in or pull-to-refresh; background backup should resume.

> Do this BEFORE testing from outside the LAN — until the headers are set, the
> apps will fail to sync whenever they're off wifi.

## Step 3 — Vaultwarden: protect the UI, bypass the client API

Create **four** applications. Cloudflare matches the most specific path first,
so the bypasses win over the catch-all.

| # | Application name | Hostname + path | Policy |
|---|---|---|---|
| 1 | `vaultwarden-api` | `vault.yourdomain.com/api` | Action **Bypass**; Include → Everyone |
| 2 | `vaultwarden-identity` | `vault.yourdomain.com/identity` | Action **Bypass**; Include → Everyone |
| 3 | `vaultwarden-notifications` | `vault.yourdomain.com/notifications/hub` | Action **Bypass**; Include → Everyone |
| 4 | `vaultwarden` (catch-all — create LAST) | `vault.yourdomain.com` | Action **Allow**; Include → Access group `household` |

Notes:
- The catch-all (#4) is what gates the web vault and `/admin`. Keep
  `VAULTWARDEN_ADMIN_TOKEN` empty in `.env` anyway (admin panel disabled) —
  Access is the outer wall, not a reason to re-enable the panel.
- "Bypass + Everyone" means those paths behave exactly as today: protected by
  your master password. That's the accepted residual risk; Step 5 rate-limits it.
- If browser-extension icon loading ever breaks after this, add a fifth bypass
  for `vault.yourdomain.com/icons`.

## Step 4 — Paperless: protect the UI, bypass the API

Same pattern, two applications (bypass first, catch-all last):

| # | Application name | Hostname + path | Policy |
|---|---|---|---|
| 1 | `paperless-api` | `paperless.yourdomain.com/api` | Action **Bypass**; Include → Everyone |
| 2 | `paperless` (catch-all) | `paperless.yourdomain.com` | Action **Allow**; Include → Access group `household` |

The mobile app keeps authenticating with its Paperless API token, unchanged.

## Step 5 — Rate-limit the bypassed API paths

The bypassed paths are the remaining app-auth-only surface; blunt brute force
against them should get throttled at the edge. Free plan includes 1 rate
limiting rule — one rule can cover both hosts:

1. Main dashboard (not Zero Trust) → `yourdomain.com` → **Security → WAF →
   Rate limiting rules → Create rule**
2. Name: `api-bruteforce-throttle`
3. Custom expression (Edit expression):
   ```
   (http.host eq "vault.yourdomain.com" and starts_with(http.request.uri.path, "/identity"))
   or (http.host eq "paperless.yourdomain.com" and starts_with(http.request.uri.path, "/api"))
   ```
   (`/identity` is where Vaultwarden login/token requests land — that's the
   brute-force target, not `/api`.)
4. Rate: **10 requests / 1 minute** per IP → Action: **Block** for 1 hour.
   (Normal client sync is well under this; raise it if a legit device trips it.)

## Step 6 — Verify

From OFF the LAN (phone on cellular, or `curl` from any VPS), or just curl —
Cloudflare answers at the edge either way:

```bash
# Protected UIs → expect 302 redirect to <team>.cloudflareaccess.com
curl -s -o /dev/null -w "%{http_code} %{redirect_url}\n" https://photos.yourdomain.com/
curl -s -o /dev/null -w "%{http_code} %{redirect_url}\n" https://vault.yourdomain.com/
curl -s -o /dev/null -w "%{http_code} %{redirect_url}\n" https://vault.yourdomain.com/admin
curl -s -o /dev/null -w "%{http_code} %{redirect_url}\n" https://paperless.yourdomain.com/

# Bypassed paths → expect the app to answer (200/4xx from the app, NOT a 302 to cloudflareaccess)
curl -s -o /dev/null -w "%{http_code}\n" https://vault.yourdomain.com/api/config
curl -s -o /dev/null -w "%{http_code}\n" https://paperless.yourdomain.com/api/

# Service token → expect 200 from Immich, not a redirect
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "CF-Access-Client-Id: <id>.access" \
  -H "CF-Access-Client-Secret: <secret>" \
  https://photos.yourdomain.com/api/server/ping
```

Then the real tests:
- [ ] Bitwarden browser extension + phone app still sync (off-wifi test on phone)
- [ ] Immich app (both phones) syncs off-wifi after headers added
- [ ] Paperless mobile app loads documents off-wifi
- [ ] Web vault in a fresh incognito window demands a Cloudflare login first

## Accepted residual risks (decisions 2026-07-12)

- **Jellyfin**: app-auth only, internet-reachable. Mitigation: stays in
  Watchtower auto-update; strong Jellyfin passwords.
- **Gitea**: app-auth only, internet-reachable. Registration disabled.
  Recommendation to remove the route or add Access stands if revisited.
- **Vaultwarden/Paperless API paths**: app-auth + edge rate limit, by protocol
  necessity (clients can't pass Access).
- **Immich LAN port `:2283`**: still bypasses all of this on the LAN — separate
  fix (split-horizon DNS, audit M7), not covered here.
