.PHONY: help dev paper live stop clean test test-integration test-replay lint format install

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install Python dependencies
	pip install -r requirements.txt
	pip install -r requirements-dev.txt

install-web: ## Install Node dependencies for web dashboard
	cd apps/web && npm install

dev: ## Start development environment (Docker)
	docker-compose up -d postgres redis
	@echo "Development infrastructure started"
	@echo "Postgres: localhost:5432"
	@echo "Redis: localhost:6379"

paper: ## Run in PAPER mode (safe simulation)
	@echo "Starting in PAPER MODE (simulation only)"
	@if [ -d "venv" ]; then \
		echo "Using virtual environment..."; \
		source venv/bin/activate; \
	fi; \
	PORT=$${PORT:-8000}; \
	export APP_MODE=PAPER; \
	python -m uvicorn apps.api.main:app --host 0.0.0.0 --port $$PORT

live: ## Run in LIVE mode (⚠️ REAL TRADING - USE WITH CAUTION)
	@echo "╔════════════════════════════════════════════════╗"
	@echo "║         ⚠️  LIVE TRADING MODE WARNING  ⚠️      ║"
	@echo "╠════════════════════════════════════════════════╣"
	@echo "║  This will execute REAL trades with REAL money ║"
	@echo "║  Losses can exceed your expectations           ║"
	@echo "║  Type exactly: CONFIRM LIVE TRADING            ║"
	@echo "╚════════════════════════════════════════════════╝"
	@read -p "Confirmation: " confirm; \
	if [ "$$confirm" = "CONFIRM LIVE TRADING" ]; then \
		export APP_MODE=LIVE && python -m apps.api.main; \
	else \
		echo "❌ Confirmation failed. Aborting."; \
		exit 1; \
	fi

stop: ## Stop all services
	docker-compose down

clean: ## Clean up containers and volumes
	docker-compose down -v
	rm -rf logs/*.log
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

test: ## Run unit tests
	pytest tests/unit -v --cov=packages --cov=apps --cov-report=term-missing

test-integration: ## Run integration tests
	pytest tests/integration -v --cov=packages --cov=apps

test-replay: ## Run replay tests on historical data
	pytest tests/replay -v

lint: ## Run linters
	ruff check packages apps
	mypy packages apps

format: ## Format code
	ruff format packages apps
	ruff check --fix packages apps

migrate: ## Run database migrations
	alembic upgrade head

burnin-report: ## Generate daily trading report
	python scripts/daily_report.py --date $$(date +%Y-%m-%d)

verify: ## Verify environment and connectivity
	python scripts/verify_env.py

smoke-test: ## Run 60-minute smoke test
	bash scripts/smoke_test.sh

rollback: ## Rollback from LIVE to PAPER
	bash scripts/rollback.sh

red-team-drills: ## Run red-team resilience drills
	bash scripts/red_team_drills.sh

failure-drills: ## Run failure drills (dual-runner, WS flap, band jump)
	bash scripts/failure_drills.sh

post-close: ## Run post-close hygiene (DB snapshot, archive logs, latency summary)
	bash scripts/post_close_hygiene.sh

live-dashboard: ## Create tmux dashboard for LIVE monitoring
	bash ops/live.sh dashboard

live-precheck: ## Run canary pre-check before LIVE switch
	bash ops/canary_precheck.sh

live-switch: ## Switch to LIVE mode
	bash ops/live.sh switch

live-full: prelive-gate ## Full LIVE sequence (gate → switch → monitor)
	bash ops/live.sh full

abort: ## Immediate abort (pause + flatten + PAPER)
	bash ops/abort.sh

paper-e2e: ## Run 30-minute PAPER end-to-end test
	python scripts/paper_e2e.py

prelive-gate: ## Run pre-LIVE gate checks (blocks switch if tripwires triggered)
	bash scripts/prelive_gate.sh

smoke-check: ## Run 2-minute smoke test after migration
	bash scripts/smoke_check.sh

quick-sanity: ## Run quick sanity checks (enum, column, endpoints)
	bash scripts/quick_sanity.sh

migration-checklist: ## Run complete migration checklist
	bash scripts/run_migration_checklist.sh

start-paper: ## Start complete PAPER session (automated)
	bash scripts/start_paper_session.sh

quick-proveout: ## Run quick prove-out test (health, metrics, kill-switch)
	bash scripts/quick_proveout.sh

quick-health: ## Run 5 critical health checks for burn-in readiness
	bash scripts/quick_health_check.sh

burnin-check: ## Quick burn-in check (leader, heartbeats, supervisor, readiness)
	bash scripts/burn_in_check.sh

reconcile-db: ## Run database reconciliation (check duplicates/orphans)
	@if [ -z "$$DATABASE_URL" ]; then \
		echo "❌ DATABASE_URL not set"; \
		exit 1; \
	fi; \
	psql "$${DATABASE_URL#postgresql+psycopg2://}" -f scripts/reconcile_db.sql

chaos-suite: ## Run full chaos test suite (leader lock, rate limit, postgres)
	@echo "🧪 Running chaos test suite..."
	@NONINTERACTIVE=1 PAUSE_ON_FAIL=1 bash scripts/chaos_test_leader_lock.sh
	@bash scripts/chaos_test_rate_limit.sh
	@bash scripts/chaos_test_postgres.sh
	@echo "✅ Chaos suite complete"

score-day1: ## One-shot Day-1 PASS scorer (readiness, heartbeats, DB integrity)
	bash scripts/score_day1.sh

score-day2: ## One-shot Day-2 PASS scorer (includes leader flaps check)
	bash scripts/score_day2.sh

print-latency: ## Print latency histogram p50/p95 (EOD sanity check)
	bash scripts/print_latency_histogram.sh

prometheus-flare: ## Print key Prometheus metrics (leader changes, order ack p95, scan HB)
	bash scripts/print_prometheus_flare.sh

read-day2: ## Read Day-2 scorer JSON and print compact PASS/FAIL line (jq-less)
	@bash scripts/read_day2_pass.sh || true

verify: ## Verify system readiness (clock drift, gate, metrics)
	@echo "🔍 Verifying system readiness..."
	@bash scripts/check_ntp_drift.sh || echo "⚠️  Clock drift check unavailable"
	@bash scripts/read_day2_pass.sh || echo "⚠️  Day-2 JSON check failed"
	@echo "✅ Verification complete"

.PHONY: verify-egress force-daily-logout sebi-verify

verify-egress: ## Verify egress IP matches expected
	@bash scripts/egress_ip_check.sh

force-daily-logout: ## Force daily logout (SEBI/NSE requirement)
	@bash scripts/force_daily_logout.sh

sebi-verify: ## Verify SEBI/NSE compliance status
	@curl -s :8000/compliance/status | jq .
	@bash scripts/prelive_gate.sh

setup-venv: ## Set up clean virtual environment with pinned dependencies
	bash scripts/setup_venv.sh

check-versions: ## Check installed dependency versions
	bash scripts/check_versions.sh

docker-build: ## Build Docker images
	docker-compose build

docker-up: ## Start all services in Docker
	docker-compose up -d

docker-logs: ## View Docker logs
	docker-compose logs -f

docker-restart: ## Restart all services
	docker-compose restart

shell-api: ## Open shell in API container
	docker-compose exec api /bin/sh

shell-postgres: ## Open PostgreSQL shell
	docker-compose exec postgres psql -U aitrapp -d aitrapp

health: ## Check system health
	@curl -s http://localhost:8000/health | python -m json.tool

metrics: ## View Prometheus metrics
	@curl -s http://localhost:8000/metrics

dashboard: ## Open dashboard in browser
	@open http://localhost:3000 || xdg-open http://localhost:3000

backup-db: ## Backup database
	@mkdir -p backups
	docker-compose exec -T postgres pg_dump -U aitrapp aitrapp > backups/aitrapp_$$(date +%Y%m%d_%H%M%S).sql
	@echo "Database backed up to backups/"

restore-db: ## Restore database (requires BACKUP_FILE=path)
	@if [ -z "$(BACKUP_FILE)" ]; then echo "Usage: make restore-db BACKUP_FILE=path/to/backup.sql"; exit 1; fi
	docker-compose exec -T postgres psql -U aitrapp aitrapp < $(BACKUP_FILE)

init: install dev migrate ## Initialize project (install deps, start infra, migrate DB)
	@echo "✅ Project initialized. Run 'make paper' to start in simulation mode."

# Kite MCP Server commands
mcp-build: ## Build Kite MCP Server (requires Go)
	@eval "$$(/opt/homebrew/bin/brew shellenv 2>/dev/null || /usr/local/bin/brew shellenv 2>/dev/null || true)" && \
	if ! command -v go &> /dev/null; then \
		echo "❌ Go is not installed. Install Go first: brew install go"; \
		echo "   Or download from: https://go.dev/dl/"; \
		exit 1; \
	fi && \
	cd kite-mcp-server && go build -o kite-mcp-server
	@echo "✅ MCP server built successfully"

mcp-setup: ## Setup MCP server environment
	@if [ ! -f kite-mcp-server/.env ]; then \
		echo "Creating MCP server .env file..."; \
		cd kite-mcp-server && \
		echo "KITE_API_KEY=$${KITE_API_KEY:-your_api_key}" > .env && \
		echo "KITE_API_SECRET=$${KITE_API_SECRET:-your_api_secret}" >> .env && \
		echo "APP_MODE=http" >> .env && \
		echo "APP_PORT=8080" >> .env && \
		echo "APP_HOST=localhost" >> .env && \
		echo "✅ MCP server .env created. Edit kite-mcp-server/.env with your API keys."; \
	else \
		echo "✅ MCP server .env already exists"; \
	fi

mcp-run: mcp-build ## Run Kite MCP Server
	@if [ ! -f kite-mcp-server/kite-mcp-server ]; then \
		echo "Building MCP server first..."; \
		$(MAKE) mcp-build; \
	fi
	@if [ ! -f kite-mcp-server/.env ]; then \
		echo "❌ .env file not found. Run: make mcp-setup"; \
		exit 1; \
	fi
	@echo "🚀 Starting Kite MCP Server on http://localhost:8080"
	@cd kite-mcp-server && export $$(grep -v '^#' .env | xargs) && ./kite-mcp-server

mcp-run-readonly: mcp-build ## Run MCP Server in read-only mode (no trading)
	@if [ ! -f kite-mcp-server/kite-mcp-server ]; then \
		echo "Building MCP server first..."; \
		$(MAKE) mcp-build; \
	fi
	@if [ ! -f kite-mcp-server/.env ]; then \
		echo "❌ .env file not found. Run: make mcp-setup"; \
		exit 1; \
	fi
	@echo "🚀 Starting Kite MCP Server (READ-ONLY) on http://localhost:8080"
	@cd kite-mcp-server && export $$(grep -v '^#' .env | xargs) && EXCLUDED_TOOLS=place_order,modify_order,cancel_order,place_gtt_order,modify_gtt_order,delete_gtt_order ./kite-mcp-server

mcp-status: ## Check MCP server status
	@curl -s http://localhost:8080/ 2>/dev/null || echo "❌ MCP server is not running"

# GitHub Actions Runner (self-hosted)
runner-setup: ## Setup self-hosted GitHub Actions runner (macOS)
	@bash scripts/setup_github_runner.sh

runner-status: ## Check runner status
	@if [ -d ~/actions-runner ]; then \
		cd ~/actions-runner && ./svc.sh status || echo "❌ Runner not installed"; \
	else \
		echo "❌ Runner directory not found. Run: make runner-setup"; \
	fi

runner-logs: ## View runner logs
	@if [ -d ~/actions-runner ]; then \
		tail -n 50 ~/actions-runner/_diag/*.log 2>/dev/null || echo "No logs found"; \
	else \
		echo "❌ Runner directory not found"; \
	fi

runner-verify: ## Verify runner setup (check all components)
	@bash scripts/verify_runner.sh
