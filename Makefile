.PHONY: help install install-dev dev run run-asgi run-daphne asgi wsgi uvicorn daphne migrate test lint clean shell docker-build docker-up docker-down start-redis stop-redis stress-redis stress-health test-auth test-common test-store test-vendor test-customer test-payments test-async test-unit test-integration test-smoke test-cov cov-html
.DEFAULT_GOAL := help

# ─── Colors ───
CYAN    := \033[0;36m
GREEN   := \033[0;32m
YELLOW  := \033[0;33m
RED     := \033[0;31m
BOLD    := \033[1m
NC      := \033[0m

##@ Help

help: ## Display this help message
	@echo "$(BOLD)$(CYAN)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo "$(BOLD)$(CYAN)  FASHIONISTAR AI — Backend Developer Commands$(NC)"
	@echo "$(CYAN)  Django 6.0 · Python 3.12+ · Dual-Engine (DRF + Ninja)$(NC)"
	@echo "$(BOLD)$(CYAN)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo ""
	@awk 'BEGIN {FS = ":.*##"; printf "Usage:\n  make $(CYAN)<target>$(NC)\n"} /^[a-zA-Z_0-9-]+:.*?##/ { printf "  $(CYAN)%-26s$(NC) %s\n", $$1, $$2 } /^##@/ { printf "\n$(YELLOW)%s$(NC)\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

# ═══════════════════════════════════════════════════════════════
##@ Development
# ═══════════════════════════════════════════════════════════════

install: ## Install Python dependencies from requirements.txt
	@echo "$(CYAN)Installing dependencies...$(NC)"
	pip install -r requirements.txt
	@echo "$(GREEN)✓ Dependencies installed$(NC)"

install-dev: ## Install dev dependencies (linting, testing, typing)
	@echo "$(CYAN)Installing dev dependencies...$(NC)"
	venv\Scripts\pip install ruff mypy pytest pytest-django pytest-asyncio pytest-cov pytest-mock factory-boy
	@echo "$(GREEN)✓ Dev dependencies installed$(NC)"

setup: install install-dev migrate static ## Full first-time setup
	@echo "$(GREEN)✓ Setup complete — run 'make dev' to start$(NC)"

dev: ## Start Django development server (sync WSGI — port 8000)
	@echo "$(CYAN)Starting Django dev server (WSGI)...$(NC)"
	venv\Scripts\python manage.py runserver

# ── ASGI / Uvicorn / Daphne shortcuts ──────────────────────────────────────
asgi: run-asgi ## Alias: start ASGI server with Uvicorn (same as run-asgi)

uvicorn: ## Start Uvicorn ASGI (production-grade async, port 8000)
	@echo "$(CYAN)Starting Uvicorn ASGI server (reload)...$(NC)"
	venv\Scripts\uvicorn backend.asgi:application --host 0.0.0.0 --port 8000 --reload --ws auto --log-level info

wsgi: ## Start Gunicorn WSGI (sync production — port 8000)
	@echo "$(CYAN)Starting Gunicorn WSGI server...$(NC)"
	venv\Scripts\gunicorn backend.wsgi:application --bind 0.0.0.0:8000 --workers 4 --timeout 120

daphne: run-daphne ## Alias: start Daphne ASGI (same as run-daphne)

run-asgi: ## Start ASGI + Uvicorn (auto-starts Redis first)
	@echo "$(CYAN)Ensuring Redis is running ...$(NC)"
	@if [ -d '../.tmp_redis' ]; then cd ../.tmp_redis && ./redis-server.exe --port 6379 & sleep 1; fi
	@echo "$(CYAN)Starting Uvicorn ASGI server...$(NC)"
	venv\Scripts\uvicorn backend.asgi:application --host 0.0.0.0 --port 8000 --reload --ws auto

run-daphne: ## Start Daphne ASGI (WebSocket — auto-starts Redis first)
	@echo "$(CYAN)Ensuring Redis is running ...$(NC)"
	@if [ -d '../.tmp_redis' ]; then cd ../.tmp_redis && ./redis-server.exe --port 6379 & sleep 1; fi
	@echo "$(CYAN)Starting Daphne ASGI server...$(NC)"
	venv\Scripts\daphne -b 0.0.0.0 -p 8000 backend.asgi:application

shell: ## Open Django interactive shell
	venv\Scripts\python manage.py shell

shell-plus: ## Open enhanced Django shell (requires django-extensions)
	venv\Scripts\python manage.py shell_plus --ipython 2>/dev/null || python manage.py shell

# ═══════════════════════════════════════════════════════════════
##@ Database & Migrations
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
##@ Database & Migrations
# ═══════════════════════════════════════════════════════════════

migrate: ## Run makemigrations + migrate
	@echo "$(CYAN)Running migrations...$(NC)"
	venv\Scripts\python manage.py makemigrations
	venv\Scripts\python manage.py migrate
	@echo "$(GREEN)✓ Migrations applied$(NC)"

mmig: ## Make migrations (optionally for a specific app: make mmig app=authentication)
	@if [ -z "$(app)" ]; then \
		venv\Scripts\python manage.py makemigrations; \
	else \
		venv\Scripts\python manage.py makemigrations "$(app)"; \
	fi

mig: ## Apply migrations (optionally for a specific app: make mig app=authentication)
	@if [ -z "$(app)" ]; then \
		venv\Scripts\python manage.py migrate; \
	else \
		venv\Scripts\python manage.py migrate "$(app)"; \
	fi

showmig: ## Show migration status for all apps
	venv\Scripts\python manage.py showmigrations

squash: ## Squash migrations for an app (usage: make squash app=authentication start=0001)
	venv\Scripts\python manage.py squashmigrations $(app) $(start)

db-reset: ## ⚠️  Reset SQLite database (destructive — dev only)
	@echo "$(RED)⚠  Resetting database...$(NC)"
	rm -f db.sqlite3
	venv\Scripts\python manage.py makemigrations
	venv\Scripts\python manage.py migrate
	@echo "$(GREEN)✓ Database reset complete$(NC)"

db-shell: ## Open database shell (dbshell)
	venv\Scripts\python manage.py dbshell

# ═══════════════════════════════════════════════════════════════
##@ Admin & Users
# ═══════════════════════════════════════════════════════════════

superuser: ## Create a Django superuser
	venv\Scripts\python manage.py createsuperuser

changepass: ## Change a user's password
	venv\Scripts\python manage.py changepassword

static: ## Collect static files
	@echo "$(CYAN)Collecting static files...$(NC)"
	venv\Scripts\python manage.py collectstatic --noinput
	@echo "$(GREEN)✓ Static files collected$(NC)"

# ═══════════════════════════════════════════════════════════════
##@ Code Quality & Linting
# ═══════════════════════════════════════════════════════════════

lint: ## Run Ruff linter on the entire project
	@echo "$(CYAN)Running Ruff linter...$(NC)"
	ruff check . --fix
	@echo "$(GREEN)✓ Linting complete$(NC)"

format: ## Format code with Ruff formatter
	@echo "$(CYAN)Formatting code...$(NC)"
	ruff format .
	@echo "$(GREEN)✓ Code formatted$(NC)"

type-check: ## Run mypy static type checking
	@echo "$(CYAN)Running mypy type check...$(NC)"
	mypy apps/ --ignore-missing-imports
	@echo "$(GREEN)✓ Type check passed$(NC)"

quality: lint format type-check ## Run all code quality checks (lint + format + types)
	@echo "$(GREEN)✓ All quality checks passed$(NC)"

# ═══════════════════════════════════════════════════════════════
##@ Testing
# ═══════════════════════════════════════════════════════════════

test: ## Run full test suite with pytest
	@echo "$(CYAN)Running tests...$(NC)"
	pytest --disable-warnings -vv -x
	@echo "$(GREEN)✓ Tests passed$(NC)"

test-cov: ## Run tests with HTML coverage report
	@echo "$(CYAN)Running tests with coverage...$(NC)"
	pytest --cov=apps --cov-report=html --cov-report=term-missing -vv
	@echo "$(GREEN)✓ Coverage report generated → htmlcov/index.html$(NC)"

test-fast: ## Run tests without warnings (fast mode)
	pytest --disable-warnings -q

test-app: ## Run tests for a specific app (usage: make test-app app=authentication)
	pytest apps/$(app)/ -vv

test-watch: ## Run tests in watch mode (requires pytest-watch)
	ptw -- --disable-warnings -vv

# ═══════════════════════════════════════════════════════════════
##@ Celery & Background Tasks
# ═══════════════════════════════════════════════════════════════

celery: ## Start Celery worker — general queue (auto-starts Redis)
	@echo "$(CYAN)Ensuring Redis is running ...$(NC)"
	@if [ -d '../.tmp_redis' ]; then cd ../.tmp_redis && ./redis-server.exe --port 6379 & sleep 1; fi
	@echo "$(CYAN)Starting Celery worker...$(NC)"
	venv\Scripts\celery -A backend worker --loglevel=info --concurrency=4

celery-emails: ## Start Celery worker for email queue (auto-starts Redis)
	@if [ -d '../.tmp_redis' ]; then cd ../.tmp_redis && ./redis-server.exe --port 6379 & sleep 1; fi
	venv\Scripts\celery -A backend worker -Q emails --loglevel=info --concurrency=2

celery-critical: ## Start Celery worker for critical queue (auto-starts Redis)
	@if [ -d '../.tmp_redis' ]; then cd ../.tmp_redis && ./redis-server.exe --port 6379 & sleep 1; fi
	venv\Scripts\celery -A backend worker -Q critical --loglevel=info --concurrency=2

celery-analytics: ## Start Celery worker for analytics queue
	venv\Scripts\celery -A backend worker -Q analytics --loglevel=info --concurrency=1

celery-beat: ## Start Celery Beat scheduler
	venv\Scripts\celery -A backend beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler

flower: ## Start Flower monitoring dashboard (port 5555)
	@echo "$(CYAN)Starting Flower at http://localhost:5555$(NC)"
	venv\Scripts\celery -A backend flower --port=5555

purge-tasks: ## ⚠️  Purge all queued Celery tasks
	@echo "$(RED)⚠  Purging all queued tasks...$(NC)"
	celery -A backend purge -f

inspect-active: ## Inspect currently active Celery tasks
	celery -A backend inspect active

inspect-stats: ## Show Celery worker statistics
	celery -A backend inspect stats

start-workers: ## Display instructions to start all workers
	@echo "$(BOLD)$(CYAN)Start each in a separate terminal:$(NC)"
	@echo "  $(CYAN)Terminal 1:$(NC) make celery"
	@echo "  $(CYAN)Terminal 2:$(NC) make celery-emails"
	@echo "  $(CYAN)Terminal 3:$(NC) make celery-critical"
	@echo "  $(CYAN)Terminal 4:$(NC) make celery-beat"
	@echo "  $(CYAN)Terminal 5:$(NC) make flower"

# ═══════════════════════════════════════════════════════════════
##@ Docker — Development
# ═══════════════════════════════════════════════════════════════

docker-build: ## Build Docker image (no cache)
	@echo "$(CYAN)Building Docker image...$(NC)"
	docker-compose build --no-cache
	@echo "$(GREEN)✓ Docker image built$(NC)"

docker-up: ## Start development containers (detached)
	@echo "$(CYAN)Starting Docker containers...$(NC)"
	docker-compose up -d
	@echo "$(GREEN)✓ Containers started$(NC)"

docker-down: ## Stop and remove containers
	@echo "$(YELLOW)Stopping containers...$(NC)"
	docker-compose down
	@echo "$(GREEN)✓ Containers stopped$(NC)"

docker-down-v: ## Stop containers and remove volumes (⚠️  data loss)
	@echo "$(RED)⚠  Stopping containers and removing volumes...$(NC)"
	docker-compose down -v

docker-restart: docker-down docker-up ## Restart all containers

docker-logs: ## Tail container logs (all services)
	docker-compose logs -f

docker-logs-web: ## Tail logs for web service only
	docker-compose logs -f web

docker-logs-celery: ## Tail logs for Celery workers
	docker-compose logs -f celery-general celery-emails celery-critical

docker-ps: ## Show running containers
	docker-compose ps

docker-exec: ## Open shell in web container
	docker-compose exec web /bin/sh

docker-exec-db: ## Open PostgreSQL shell in db container
	docker-compose exec db psql -U $${DB_USER:-postgres} -d $${DB_NAME:-fashionistar}

docker-rebuild: ## Full rebuild (stop → clean → build → start)
	@echo "$(CYAN)Full Docker rebuild...$(NC)"
	docker-compose down -v
	docker-compose build --no-cache
	docker-compose up -d
	@echo "$(GREEN)✓ Full rebuild complete$(NC)"
	docker-compose logs -f

# ═══════════════════════════════════════════════════════════════
##@ Docker — Production
# ═══════════════════════════════════════════════════════════════

prod-up: ## Start production environment
	@echo "$(CYAN)Starting production environment...$(NC)"
	docker-compose -f docker-compose.production.yml up -d --build
	@echo "$(GREEN)✓ Production environment started$(NC)"

prod-down: ## Stop production environment
	docker-compose -f docker-compose.production.yml down

prod-logs: ## Tail production logs
	docker-compose -f docker-compose.production.yml logs -f

prod-restart: prod-down prod-up ## Restart production environment

# ═══════════════════════════════════════════════════════════════
##@ Infrastructure
# ═══════════════════════════════════════════════════════════════

infra-up: ## Start Redis + PostgreSQL locally via Docker
	@echo "$(CYAN)Starting infrastructure services...$(NC)"
	docker run -d --name fashionistar-redis -p 6379:6379 redis:7-alpine || echo "$(YELLOW)Redis already running$(NC)"
	docker run -d --name fashionistar-postgres -p 5432:5432 \
		-e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=fashionistar \
		postgres:17-alpine || echo "$(YELLOW)PostgreSQL already running$(NC)"
	@echo "$(GREEN)✓ Infrastructure ready$(NC)"

infra-down: ## Stop infrastructure containers
	docker stop fashionistar-redis fashionistar-postgres 2>/dev/null || true
	docker rm fashionistar-redis fashionistar-postgres 2>/dev/null || true
	@echo "$(GREEN)✓ Infrastructure stopped$(NC)"

# ═══════════════════════════════════════════════════════════════
##@ Local Redis (Windows Portable)
# ═══════════════════════════════════════════════════════════════

start-redis: ## Start local portable Redis server on port 6379 (background)
	@echo "$(CYAN)Starting local portable Redis server...$(NC)"
	@if [ -d "../.tmp_redis" ]; then \
		cd ../.tmp_redis && ./redis-server.exe --port 6379 & \
		echo "$(GREEN)✓ Redis started on 127.0.0.1:6379$(NC)"; \
	else \
		echo "$(RED)✗ Redis not found at ../.tmp_redis$(NC)"; \
	fi

stop-redis: ## Stop local portable Redis server
	@echo "$(CYAN)Stopping local portable Redis server...$(NC)"
	taskkill /F /IM redis-server.exe /T 2>NUL || echo "$(YELLOW)Redis is not running$(NC)"
	@echo "$(GREEN)✓ Redis stopped$(NC)"

# ═══════════════════════════════════════════════════════════════
##@ Health Checks & Monitoring
# ═══════════════════════════════════════════════════════════════

health: ## Check API health endpoint
	@echo "$(CYAN)Checking system health...$(NC)"
	@curl -sf http://localhost:8000/health/ | python -m json.tool 2>/dev/null || echo "$(RED)✗ API not running on port 8000$(NC)"

health-redis: ## Check Redis connectivity
	@echo "$(CYAN)Checking Redis...$(NC)"
	@python -c "import redis; r = redis.from_url('$${REDIS_URL:-redis://localhost:6379/0}'); r.ping(); print('\033[0;32m✓ Redis connected\033[0m')" 2>/dev/null || echo "$(RED)✗ Redis not available$(NC)"

test-metrics: ## Check Prometheus metrics endpoint
	@echo "$(CYAN)Testing metrics...$(NC)"
	@curl -sf http://localhost:8000/metrics/ | head -10 || echo "$(RED)✗ Metrics endpoint not available$(NC)"

# ═══════════════════════════════════════════════════════════════
##@ CI/CD Pipeline
# ═══════════════════════════════════════════════════════════════

ci: quality test ## Run full CI pipeline (lint + format + types + tests)
	@echo "$(GREEN)✓ CI pipeline passed$(NC)"

ci-fast: lint test-fast ## Run fast CI pipeline (lint + quick tests)
	@echo "$(GREEN)✓ Fast CI pipeline passed$(NC)"

pre-commit: quality ## Pre-commit hook: run all quality checks
	@echo "$(GREEN)✓ Pre-commit checks passed$(NC)"

# ═══════════════════════════════════════════════════════════════
##@ Cleanup
# ═══════════════════════════════════════════════════════════════

clean: ## Remove Python cache files (.pyc, __pycache__)
	@echo "$(YELLOW)Cleaning Python cache...$(NC)"
	find . -type f -name '*.pyc' -delete
	find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name '.mypy_cache' -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name '.pytest_cache' -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov/ .coverage
	@echo "$(GREEN)✓ Cleaned$(NC)"

clean-docker: ## Remove all Docker containers, images, and volumes
	@echo "$(RED)⚠  Cleaning all Docker resources...$(NC)"
	docker-compose down -v
	docker rmi $$(docker images -q --filter "reference=fashionistar*") 2>/dev/null || true
	@echo "$(GREEN)✓ Docker cleaned$(NC)"

clean-all: clean clean-docker ## Nuclear clean (Python cache + Docker)
	@echo "$(GREEN)✓ Everything cleaned$(NC)"

# ═══════════════════════════════════════════════════════════════
##@ Environment & Configuration
# ═══════════════════════════════════════════════════════════════

env-setup: ## Create .env from .env.example (safe — won't overwrite)
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "$(GREEN)✓ Created .env from .env.example — edit with your secrets$(NC)"; \
	else \
		echo "$(YELLOW)⚠ .env already exists — skipped$(NC)"; \
	fi

env-check: ## Display current environment configuration
	@echo "$(CYAN)Current environment:$(NC)"
	@if [ -f .env ]; then \
		grep -v '^\s*#' .env | grep -v '^\s*$$' | sed 's/=.*/=***/' ; \
	else \
		echo "$(RED)✗ .env not found — run 'make env-setup'$(NC)"; \
	fi

# ═══════════════════════════════════════════════════════════════
##@ Project Information
# ═══════════════════════════════════════════════════════════════

info: ## Display project information
	@echo "$(BOLD)$(CYAN)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo "$(BOLD)  FASHIONISTAR AI — Backend$(NC)"
	@echo "$(CYAN)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"
	@echo "  Python:       $$(python --version 2>&1)"
	@echo "  Django:       $$(python -c 'import django; print(django.VERSION)' 2>/dev/null || echo 'not installed')"
	@echo "  Architecture: Dual-Engine (DRF Sync + Ninja Async)"
	@echo "  Database:     PostgreSQL 17 / SQLite (dev)"
	@echo "  Cache:        Redis"
	@echo "  Task Engine:  Celery → Django 6.0 Native Tasks"
	@echo "  API Docs:     http://localhost:8000/swagger/"
	@echo "$(CYAN)━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━$(NC)"

urls: ## Display key API endpoints
	@echo "$(BOLD)$(CYAN)Key Endpoints:$(NC)"
	@echo "  $(CYAN)API Root:$(NC)     http://localhost:8000/api/"
	@echo "  $(CYAN)Swagger:$(NC)      http://localhost:8000/swagger/"
	@echo "  $(CYAN)ReDoc:$(NC)        http://localhost:8000/redoc/"
	@echo "  $(CYAN)Admin:$(NC)        http://localhost:8000/$${DJANGO_SECRET_ADMIN_URL:-admin/}"
	@echo "  $(CYAN)Ninja Async:$(NC)  http://localhost:8000/api/v2/"

deps: ## List installed Python packages
	pip list --format=columns

outdated: ## Check for outdated Python packages
	pip list --outdated

req-update: ## Freeze current packages to requirements.txt
	@echo "$(YELLOW)⚠  Updating requirements.txt from installed packages...$(NC)"
	pip freeze > requirements.txt
	@echo "$(GREEN)✓ requirements.txt updated$(NC)"

# ═══════════════════════════════════════════════════════════════
##@ Quick Commands
# ═══════════════════════════════════════════════════════════════

quick-start: env-setup install install-dev migrate static dev ## 🚀 First-time setup → run

quick-docker: docker-build docker-up ## 🐳 Build and start Docker

quick-test: lint test-cov ## 🧪 Lint + test with coverage

full-reset: clean db-reset install migrate static ## 🔄 Nuclear reset → fresh start
	@echo "$(GREEN)✓ Full reset complete — run 'make dev' to start$(NC)"

dashboards: ## 📊 Show all service URLs
	@echo "$(BOLD)$(CYAN)━━━ Service Dashboards ━━━$(NC)"
	@echo "  $(CYAN)Django API:$(NC)   http://localhost:8000"
	@echo "  $(CYAN)Swagger UI:$(NC)   http://localhost:8000/swagger/"
	@echo "  $(CYAN)Admin:$(NC)        http://localhost:8000/$${DJANGO_SECRET_ADMIN_URL:-admin/}"
	@echo "  $(CYAN)Flower:$(NC)       http://localhost:5555"
	@echo "  $(CYAN)Prometheus:$(NC)   http://localhost:9090"
	@echo "  $(CYAN)Grafana:$(NC)      http://localhost:3000"