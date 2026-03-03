.PHONY: update-gluetun help

# Services that use network_mode: service:gluetun
GLUETUN_DEPS = qbittorrent sabnzbd prowlarr radarr sonarr

# Update gluetun: pull latest image, recreate container, restart all dependents
update-gluetun:
	@echo "🔄 Pulling latest gluetun image..."
	docker compose pull gluetun
	@echo "🛑 Stopping gluetun dependents..."
	docker compose stop $(GLUETUN_DEPS)
	docker compose rm -f $(GLUETUN_DEPS)
	@echo "♻️  Recreating gluetun..."
	docker compose up -d gluetun
	@echo "⏳ Waiting for gluetun to be healthy..."
	@until docker inspect --format='{{.State.Health.Status}}' gluetun 2>/dev/null | grep -q healthy; do sleep 2; done
	@echo "🚀 Starting dependents..."
	docker compose up -d $(GLUETUN_DEPS)
	@echo "✅ Gluetun and all dependents updated."

help:
	@echo "Mediaserver Makefile"
	@echo ""
	@echo "  update-gluetun  - Pull latest gluetun image and recreate container"
	@echo "  help            - Show this help"

all: help
