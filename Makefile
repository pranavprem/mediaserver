.PHONY: update-gluetun help

# Update gluetun: pull latest image, recreate container, restart dependents
update-gluetun:
	@echo "🔄 Pulling latest gluetun image..."
	docker compose pull gluetun
	@echo "♻️  Recreating gluetun (dependents will restart via Watchtower labels)..."
	docker compose up -d gluetun
	@echo "✅ Gluetun updated."

help:
	@echo "Mediaserver Makefile"
	@echo ""
	@echo "  update-gluetun  - Pull latest gluetun image and recreate container"
	@echo "  help            - Show this help"

all: help
