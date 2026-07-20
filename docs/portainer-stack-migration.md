# Portainer Stack Migration

Goal: make Portainer manage the whole media stack as a stack, not just individual containers.

Portainer needs to own/import the compose definition before it can restart or redeploy a full stack. Seeing containers through the Docker socket is not enough.

## Target Layout

- `portainer` is a standalone bootstrap stack from `portainer-compose.yaml`.
- `mediaserver` is a Git-backed Portainer stack from `docker-compose.yaml`.
- Other compose projects should follow the same pattern: one repo, one explicit compose project name, one Portainer stack.

`docker-compose.yaml` now pins the compose project name with:

```yaml
name: mediaserver
```

That keeps Portainer aligned with the existing NAS containers that were created from `/volume1/docker/mediaserver`.

## Migration

Run these from the NAS in `/volume1/docker/mediaserver`.

1. Pull the updated repo:

```bash
git checkout private
git pull origin private
```

1. If Portainer is currently running from the old `mediaserver` compose file, detach it from that stack:

```bash
docker compose stop portainer
docker compose rm -f portainer
```

This does not delete Portainer data because data lives under `${CONFIG_ROOT}/portainer`.

1. Start the standalone Portainer bootstrap stack:

```bash
make portainer-up
```

1. Open Portainer and create a stack:

- Name: `mediaserver`
- Build method: Git repository
- Repository URL: `http://10.0.0.116:41234/pranav-gitea/mediaserver.git`
- Repository reference: `refs/heads/private`
- Compose path: `docker-compose.yaml`
- Environment: load or paste the existing values from `/volume1/docker/mediaserver/.env`

1. Deploy the stack.

Because the compose project name is pinned to `mediaserver` and the service/container names did not change, Compose should converge on the existing containers and persistent bind mounts instead of creating a second copy of the stack.

## Operating Rules

- Use Portainer for full-stack restart, stop, start, and Git redeploy of `mediaserver`.
- Keep Portainer outside the `mediaserver` stack so a media-stack redeploy does not take down the UI that is driving it.
- Do not use Watchtower or a generic Portainer recreate for `gluetun` image updates. Use `make update-gluetun`, because the download and Arr containers use `network_mode: service:gluetun`.
- Before importing another compose repo into Portainer, add a stable top-level `name:` matching the intended Portainer stack name.

## Suggested Stack Names

Give each imported compose project a stable top-level `name:` matching its
Portainer stack name, e.g.:

- `mediaserver`
- `<your-other-stack>`
