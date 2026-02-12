#!/bin/bash
# Updates gluetun and restarts all dependent containers via docker compose.
# Watchtower can't handle network_mode dependencies properly, so gluetun
# is excluded from Watchtower and updated via this script instead.
#
# Add to crontab: 0 5 * * * /volume1/docker/mediaserver/scripts/update-gluetun.sh
#
set -euo pipefail

COMPOSE_DIR="/volume1/docker/mediaserver"
cd "$COMPOSE_DIR"

# Pull latest gluetun image
BEFORE=$(docker inspect gluetun --format '{{.Image}}' 2>/dev/null || echo "none")
docker compose pull gluetun

AFTER=$(docker inspect gluetun --format '{{.Image}}' 2>/dev/null || echo "none")

# Only restart if image changed, or force with --force flag
if [ "$BEFORE" != "$AFTER" ] || [ "${1:-}" = "--force" ]; then
    echo "$(date): Gluetun image updated, restarting stack..."
    docker compose up -d
    echo "$(date): Done."
else
    echo "$(date): Gluetun already up to date."
fi
