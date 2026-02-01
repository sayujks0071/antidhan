# OpenAlgo Makefile

.PHONY: all obs-up obs-down obs-logs run status help

all: help

help:
	@echo "OpenAlgo Management Commands"
	@echo "----------------------------"
	@echo "make obs-up       : Start Observability Stack (Loki, Promtail, Grafana)"
	@echo "make obs-down     : Stop Observability Stack"
	@echo "make obs-logs     : Tail Promtail logs and OpenAlgo app logs"
	@echo "make run          : Run OpenAlgo daily startup"
	@echo "make status       : Check health of OpenAlgo and Observability"
	@echo "make install-obs  : Install healthcheck schedulers"

obs-up:
	docker compose -f observability/docker-compose.yml up -d
	@echo "Observability Stack Started. Grafana at http://localhost:3000"

obs-down:
	docker compose -f observability/docker-compose.yml down

obs-logs:
	@echo "Tailing Promtail logs and App logs (Ctrl+C to stop)..."
	@(trap 'kill 0' SIGINT; tail -f logs/openalgo.log & docker compose -f observability/docker-compose.yml logs -f promtail)

run:
	python3 daily_startup.py

status:
	@echo "--- Docker Services ---"
	docker compose -f observability/docker-compose.yml ps
	@echo "\n--- Health Check ---"
	python3 scripts/healthcheck.py

install-obs:
	./scripts/install_systemd_user_timers.sh
