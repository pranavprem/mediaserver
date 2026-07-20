# Portainer Clean Restart Snippet

Use `stack-ops-compose.yaml` as a Portainer stack named `stack-ops`.

This gives Portainer a one-shot container called `stack-clean-restart`. Start that container whenever you want to cleanly restart all currently running stacks.

## What It Does

- Finds running Docker Compose / Portainer stacks from container labels.
- Skips `portainer` and `stack-ops` by default.
- Stops only containers that were running when the job started.
- Starts `gluetun` first and waits for it to become healthy before starting its dependents.
- Starts the remaining containers for each stack.

It does not start optional services that were already stopped.

## Create It In Portainer

1. Go to **Stacks**.
2. Create a stack named `stack-ops`.
3. Paste the contents of `stack-ops-compose.yaml`.
4. Deploy it.

The job container should run once and exit.

## Run It Again Later

Go to **Containers** and start `stack-clean-restart`.

## Dry Run

Set:

```yaml
DRY_RUN: "true"
```

Then redeploy/start the job to see what it would restart without touching containers.

## Security Note

This stack mounts `/var/run/docker.sock` read-write because restarting containers requires Docker API write access. Keep this stack local-only and do not attach it to any network.
