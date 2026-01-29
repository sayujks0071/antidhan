.PHONY: obs-up obs-down obs-logs run status help install-monitoring uninstall-monitoring

help:
	@echo "OpenAlgo Observability Commands"
	@echo "  make obs-up              Start observability stack (Loki/Grafana/Promtail)"
	@echo "  make obs-down            Stop observability stack"
	@echo "  make obs-logs            Tail logs from Promtail and App"
	@echo "  make run                 Run OpenAlgo app (with logging)"
	@echo "  make status              Check status of stack"
	@echo "  make install-monitoring  Install scheduled health checks (systemd/cron)"
	@echo "  make uninstall-monitoring Remove scheduled health checks"

obs-up:
	docker compose -f observability/docker-compose.yml up -d
	@echo "Grafana is running at http://localhost:3000 (admin/admin)"

obs-down:
	docker compose -f observability/docker-compose.yml down

obs-logs:
	@echo "Tailing app logs (local) and stack logs (docker)... (Ctrl+C to stop)"
	@bash -c "trap 'kill 0' SIGINT; docker compose -f observability/docker-compose.yml logs -f & tail -f logs/openalgo.log & wait"

run:
	@echo "Starting OpenAlgo..."
	python3 -m openalgo.app

status:
	@echo "=== Docker Services ==="
	@docker compose -f observability/docker-compose.yml ps
	@echo "\n=== Health Check ==="
	@python3 scripts/healthcheck.py

install-monitoring:
	@./scripts/install_systemd_user_timers.sh || ./scripts/install_cron.sh

uninstall-monitoring:
	@./scripts/uninstall_schedulers.sh
