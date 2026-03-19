include .env
export

.PHONY: update-gluetun sync-configs sync-prometheus sync-recyclarr sync-grafana help

# Services that use network_mode: service:gluetun
GLUETUN_DEPS = qbittorrent sabnzbd prowlarr radarr sonarr

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
	docker compose restart prometheus
	@echo "✅ Prometheus config updated and restarted."

# Sync Recyclarr config and restart
sync-recyclarr:
	@echo "♻️  Syncing recyclarr.yml → $(CONFIG_ROOT)/recyclarr/"
	@mkdir -p $(CONFIG_ROOT)/recyclarr
	cp recyclarr.yml $(CONFIG_ROOT)/recyclarr/recyclarr.yml
	chmod 644 $(CONFIG_ROOT)/recyclarr/recyclarr.yml
	docker compose restart recyclarr
	@echo "✅ Recyclarr config updated and restarted."

# Reload Grafana dashboards (provisioned from repo, restart picks up changes)
sync-grafana:
	@echo "📊 Reloading Grafana dashboards..."
	docker compose restart grafana
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

# ─── Help ────────────────────────────────────────────────────────────────────

help:
	@echo "Mediaserver Makefile"
	@echo ""
	@echo "  sync-configs    - Sync all repo configs to CONFIG_ROOT and restart services"
	@echo "  sync-prometheus - Sync prometheus.yml and restart Prometheus"
	@echo "  sync-recyclarr  - Sync recyclarr.yml and restart Recyclarr"
	@echo "  sync-grafana    - Reload Grafana dashboards from repo"
	@echo "  update-gluetun  - Pull latest gluetun image and restart with dependents"
	@echo "  help            - Show this help"

all: help
