include .env
export

.PHONY: up down restart logs ps update-gluetun sync-configs sync-prometheus sync-recyclarr recyclarr-preview setup-recyclarr setup-bazarr sync-grafana paperless-validate setup-paperless paperless-up paperless-down paperless-restart paperless-logs paperless-status paperless-health paperless-reset-perms paperless-backup paperless-superuser paperless-shell help

# Services that use network_mode: service:gluetun
GLUETUN_DEPS = qbittorrent sabnzbd prowlarr radarr sonarr bazarr
BAZARR_DEFAULT_URL ?= http://127.0.0.1:$(BAZARR_PORT)
PAPERLESS_INTAKE_PATH ?= $(DOCUMENTS_ROOT)/consume

# ─── Stack Wrappers ──────────────────────────────────────────────────────────

up:
	@echo "🚀 Starting mediaserver stack..."
	docker compose up -d
	@echo "✅ Mediaserver stack started."

down:
	@echo "🛑 Bringing mediaserver stack down..."
	docker compose down
	@echo "✅ Mediaserver stack stopped."

restart:
	@echo "♻️  Restarting mediaserver stack..."
	docker compose restart
	@echo "✅ Mediaserver stack restarted."

logs:
	docker compose logs --tail=200 -f

ps:
	docker compose ps

# ─── Config Sync ─────────────────────────────────────────────────────────────

# Sync all repo configs to CONFIG_ROOT and restart affected services
sync-configs: sync-prometheus sync-recyclarr sync-grafana
	@echo "✅ All configs synced."

# Sync Prometheus config and restart
sync-prometheus:
	@echo "📊 Syncing prometheus.yml → $(CONFIG_ROOT)/prometheus/"
	@mkdir -p $(CONFIG_ROOT)/prometheus
	cp prometheus.yml $(CONFIG_ROOT)/prometheus/prometheus.yml
	chmod 644 $(CONFIG_ROOT)/prometheus/prometheus.yml
	docker restart prometheus
	@echo "✅ Prometheus config updated and restarted."

# Render Recyclarr config with live API keys and ensure the container is running
sync-recyclarr:
	@echo "♻️  Rendering recyclarr.yml → $(CONFIG_ROOT)/recyclarr/recyclarr.yml"
	@test -n "$(CONFIG_ROOT)" && [ "$(CONFIG_ROOT)" != "/path/to/config" ] || (echo "❌ Set CONFIG_ROOT in .env first." && exit 1)
	@test -f "$(CONFIG_ROOT)/sonarr/config.xml" || (echo "❌ Missing $(CONFIG_ROOT)/sonarr/config.xml. Start Sonarr first." && exit 1)
	@test -f "$(CONFIG_ROOT)/radarr/config.xml" || (echo "❌ Missing $(CONFIG_ROOT)/radarr/config.xml. Start Radarr first." && exit 1)
	@mkdir -p $(CONFIG_ROOT)/recyclarr
	@python3 scripts/render_recyclarr_config.py "$(CONFIG_ROOT)"
	@chmod 600 $(CONFIG_ROOT)/recyclarr/recyclarr.yml
	@docker compose up -d recyclarr
	@echo "✅ Recyclarr config rendered and container ensured running."

# Preview adoption + sync without changing Sonarr/Radarr
recyclarr-preview: sync-recyclarr
	@echo "🔍 Previewing Recyclarr state repair/adoption..."
	@docker exec recyclarr recyclarr state repair --adopt --preview
	@echo "🔍 Previewing Recyclarr sync..."
	@docker exec recyclarr recyclarr sync --preview
	@echo "✅ Preview complete."

# One-shot Recyclarr setup: render config, adopt existing Arr state, then sync
setup-recyclarr: sync-recyclarr
	@echo "🛠️  Repairing Recyclarr state and adopting existing Arr resources..."
	@docker exec recyclarr recyclarr state repair --adopt
	@echo "♻️  Running Recyclarr sync..."
	@docker exec recyclarr recyclarr sync
	@echo "✅ Recyclarr profiles synced to Sonarr + Radarr."

# One-shot Bazarr setup: start services, wire Sonarr/Radarr, and seed default subtitle profile
setup-bazarr:
	@echo "🈂️  Starting Bazarr + Arr services needed for bootstrap..."
	@test -n "$(CONFIG_ROOT)" && [ "$(CONFIG_ROOT)" != "/path/to/config" ] || (echo "❌ Set CONFIG_ROOT in .env first." && exit 1)
	docker compose up -d gluetun sonarr radarr bazarr
	@BAZARR_URL="$(BAZARR_DEFAULT_URL)" python3 scripts/setup_bazarr.py "$(CONFIG_ROOT)"
	@echo "✅ Bazarr configured with default English + Spanish subtitles."
	@echo "➡️  Next: add subtitle providers in Bazarr at $(BAZARR_DEFAULT_URL) for actual subtitle downloads."

# Reload Grafana dashboards (provisioned from repo, restart picks up changes)
sync-grafana:
	@echo "📊 Reloading Grafana dashboards..."
	docker restart grafana
	@echo "✅ Grafana dashboards reloaded."

# ─── Gluetun Update ─────────────────────────────────────────────────────────

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

# ─── Paperless Bootstrap ────────────────────────────────────────────────────

PAPERLESS_SERVICES = paperless-postgres paperless-redis paperless-gotenberg paperless-tika paperless-webserver
PAPERLESS_BACKUP_ROOT ?= $(DOCUMENTS_ROOT)/backups

paperless-validate:
	@echo "📄 Validating Paperless environment..."
	@test -n "$(CONFIG_ROOT)" && [ "$(CONFIG_ROOT)" != "/path/to/config" ] || (echo "❌ Set CONFIG_ROOT in .env first." && exit 1)
	@test -n "$(DOCUMENTS_ROOT)" && [ "$(DOCUMENTS_ROOT)" != "/path/to/documents" ] || (echo "❌ Set DOCUMENTS_ROOT in .env first." && exit 1)
	@test -n "$(PAPERLESS_URL)" && [ "$(PAPERLESS_URL)" != "https://paperless.yourdomain.com" ] || (echo "❌ Set PAPERLESS_URL in .env first." && exit 1)
	@test -n "$(PAPERLESS_SECRET_KEY)" || (echo "❌ Set PAPERLESS_SECRET_KEY in .env first." && exit 1)
	@test -n "$(PAPERLESS_DB_PASSWORD)" || (echo "❌ Set PAPERLESS_DB_PASSWORD in .env first." && exit 1)
	@test -n "$(PAPERLESS_REDIS_PASSWORD)" || (echo "❌ Set PAPERLESS_REDIS_PASSWORD in .env first." && exit 1)

# Create Paperless directories on the NAS, then start the document stack
setup-paperless: paperless-validate
	@echo "📁 Creating Paperless directories..."
	@mkdir -p $(CONFIG_ROOT)/paperless/data $(CONFIG_ROOT)/paperless/postgres $(CONFIG_ROOT)/paperless/redis
	@mkdir -p $(DOCUMENTS_ROOT)/media $(DOCUMENTS_ROOT)/export $(PAPERLESS_BACKUP_ROOT) $(PAPERLESS_INTAKE_PATH)
	@$(MAKE) paperless-up
	@echo "✅ Paperless directories created and services started."
	@echo "➡️  Next: add a Cloudflare Tunnel public hostname for $(PAPERLESS_URL) -> http://paperless-webserver:8000"
	@echo "➡️  Then: make paperless-superuser"
	@echo "➡️  Finally: create a separate Paperless login for Abhinaya"

paperless-up: paperless-validate
	@echo "🚀 Starting Paperless services..."
	docker compose up -d $(PAPERLESS_SERVICES)
	@echo "✅ Paperless services started."

paperless-down:
	@echo "🛑 Stopping Paperless services..."
	docker compose stop $(PAPERLESS_SERVICES)
	@echo "✅ Paperless services stopped."

paperless-restart:
	@$(MAKE) paperless-down
	@$(MAKE) paperless-up

paperless-logs:
	docker compose logs --tail=200 -f $(PAPERLESS_SERVICES)

paperless-status:
	docker compose ps $(PAPERLESS_SERVICES)

paperless-health:
	@echo "🩺 Paperless container health:"
	@for svc in $(PAPERLESS_SERVICES); do \
		cid=$$(docker compose ps -q $$svc 2>/dev/null); \
		if [ -z "$$cid" ]; then \
			echo "  $$svc: not created"; \
		else \
			status=$$(docker inspect --format='{{.State.Status}}' $$cid 2>/dev/null); \
			health=$$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}' $$cid 2>/dev/null); \
			echo "  $$svc: $$status (health=$$health)"; \
		fi; \
	done

paperless-reset-perms: paperless-validate
	@echo "🔐 Resetting Paperless web/storage permissions (leaving postgres/redis data alone)..."
	@mkdir -p $(CONFIG_ROOT)/paperless/data $(DOCUMENTS_ROOT)/media $(DOCUMENTS_ROOT)/export $(PAPERLESS_BACKUP_ROOT) $(PAPERLESS_INTAKE_PATH)
	chown -R $(PUID):$(PGID) $(CONFIG_ROOT)/paperless/data $(DOCUMENTS_ROOT)/media $(DOCUMENTS_ROOT)/export $(PAPERLESS_BACKUP_ROOT) $(PAPERLESS_INTAKE_PATH)
	@echo "✅ Paperless web/storage permissions reset."

paperless-backup: paperless-up
	@echo "💾 Creating Paperless backup..."
	@mkdir -p $(PAPERLESS_BACKUP_ROOT)
	@TS=$$(date +%Y%m%d-%H%M%S); \
	DEST="$(PAPERLESS_BACKUP_ROOT)/paperless-$$TS"; \
	DB_USER="$${PAPERLESS_DB_USERNAME:-paperless}"; \
	DB_NAME="$${PAPERLESS_DB_DATABASE:-paperless}"; \
	INTAKE_PATH="$(PAPERLESS_INTAKE_PATH)"; \
	DOCS_ROOT="$(DOCUMENTS_ROOT)"; \
	mkdir -p "$$DEST"; \
	echo "  → $$DEST"; \
	docker compose exec -T paperless-postgres pg_dump -U "$$DB_USER" -d "$$DB_NAME" > "$$DEST/postgres.sql"; \
	tar -C "$(CONFIG_ROOT)/paperless" -czf "$$DEST/config-data.tgz" data; \
	if [ "$$INTAKE_PATH" = "$$DOCS_ROOT/consume" ]; then \
		tar -C "$$DOCS_ROOT" -czf "$$DEST/documents.tgz" media consume export; \
	else \
		tar -C "$$DOCS_ROOT" -czf "$$DEST/documents.tgz" media export; \
		if [ -d "$$INTAKE_PATH" ]; then \
			tar -C "$$(dirname "$$INTAKE_PATH")" -czf "$$DEST/intake.tgz" "$$(basename "$$INTAKE_PATH")"; \
		fi; \
	fi; \
	echo "✅ Backup written to $$DEST"

paperless-superuser: paperless-up
	@echo "👤 Launching Paperless superuser creation..."
	docker compose exec paperless-webserver python manage.py createsuperuser

paperless-shell: paperless-up
	@echo "🐚 Opening shell in paperless-webserver..."
	docker compose exec paperless-webserver /bin/sh

# ─── Help ────────────────────────────────────────────────────────────────────

help:
	@echo "Mediaserver Makefile"
	@echo ""
	@echo "  up                   - Start the full mediaserver stack"
	@echo "  down                 - Bring the full mediaserver stack down"
	@echo "  restart              - Restart the full mediaserver stack"
	@echo "  logs                 - Tail logs for the full mediaserver stack"
	@echo "  ps                   - Show full mediaserver container status"
	@echo "  sync-configs         - Sync all repo configs to CONFIG_ROOT and restart services"
	@echo "  sync-prometheus      - Sync prometheus.yml and restart Prometheus"
	@echo "  sync-recyclarr       - Render recyclarr.yml with live Arr API keys and ensure Recyclarr is running"
	@echo "  recyclarr-preview    - Preview Recyclarr adoption + sync without changing Sonarr/Radarr"
	@echo "  setup-recyclarr      - One-shot Recyclarr setup, adopt existing Arr state, and sync TRaSH profiles"
	@echo "  setup-bazarr         - Start Bazarr, wire Sonarr/Radarr, and seed default English+Spanish subtitles"
	@echo "  sync-grafana         - Reload Grafana dashboards from repo"
	@echo "  setup-paperless      - Create Paperless dirs on NAS and start the document stack"
	@echo "  paperless-up         - Start all Paperless services"
	@echo "  paperless-down       - Stop all Paperless services"
	@echo "  paperless-restart    - Restart all Paperless services"
	@echo "  paperless-status     - Show Paperless container status"
	@echo "  paperless-health     - Show Paperless runtime/health status"
	@echo "  paperless-logs       - Tail logs for all Paperless services"
	@echo "  paperless-reset-perms - Fix ownership for Paperless web/storage dirs"
	@echo "  paperless-backup     - Create a timestamped Paperless backup"
	@echo "  paperless-superuser  - Run Paperless createsuperuser"
	@echo "  paperless-shell      - Open a shell in paperless-webserver"
	@echo "  update-gluetun       - Pull latest gluetun image and restart with dependents"
	@echo "  help                 - Show this help"

all: help
