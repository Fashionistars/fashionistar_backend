ifneq (,$(wildcard ./.env))
include .env
export
ENV_FILE_PARAM = --env-file .env
endif

.PHONY: help install dev run run-asgi migrate test lint clean shell docker-build docker-up docker-down
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
	@awk 'BEGIN {FS = ":.*##"; printf "Usage:\n  make $(CYAN)<target>$(NC)\n"} /^[a-zA-Z_0-9-]+:.*?##/ { printf "  $(CYAN)%-22s$(NC) %s\n", $$1, $$2 } /^##@/ { printf "\n$(YELLOW)%s$(NC)\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

# ═══════════════════════════════════════════════════════════════
##@ Development
# ═══════════════════════════════════════════════════════════════

install: ## Install Python dependencies from requirements.txt
	@echo "$(CYAN)Installing dependencies...$(NC)"
	pip install -r requirements.txt
	@echo "$(GREEN)✓ Dependencies installed$(NC)"

install-dev: ## Install dev dependencies (linting, testing, typing)
	@echo "$(CYAN)Installing dev dependencies...$(NC)"
	pip install ruff mypy pytest pytest-django pytest-asyncio pytest-cov
	@echo "$(GREEN)✓ Dev dependencies installed$(NC)"

setup: install install-dev migrate static ## Full first-time setup
	@echo "$(GREEN)✓ Setup complete — run 'make dev' to start$(NC)"

dev: ## Start Django development server (sync — port 8000)
	@echo "$(CYAN)Starting Django dev server...$(NC)"
	python manage.py runserver 0.0.0.0:8000

vir-dev: ## Start Django development server (sync — port 8000)
	@echo "$(CYAN)Starting Django dev server...$(NC)"
	source env/Scripts/activate
	python manage.py runserver 0.0.0.0:8000

# run: dev ## Alias for 'make dev'

run-asgi: ## Start ASGI server with Uvicorn (async — port 8000)
	@echo "$(CYAN)Starting Uvicorn ASGI server...$(NC)"
	uvicorn backend.asgi:application --host 0.0.0.0 --port 8000 --reload --ws auto

run-daphne: ## Start Daphne ASGI server (WebSocket support — port 8000)
	@echo "$(CYAN)Starting Daphne ASGI server...$(NC)"
	daphne -b 0.0.0.0 -p 8000 backend.asgi:application

shell: ## Open Django interactive shell
	python manage.py shell

shell-plus: ## Open enhanced Django shell (requires django-extensions)
	python manage.py shell_plus --ipython 2>/dev/null || python manage.py shell

# ═══════════════════════════════════════════════════════════════
##@ Database & Migrations
# ═══════════════════════════════════════════════════════════════

migrate: ## Run makemigrations + migrate
	@echo "$(CYAN)Running migrations...$(NC)"
	python manage.py makemigrations
	python manage.py migrate
	@echo "$(GREEN)✓ Migrations applied$(NC)"

mmig: ## Make migrations (optionally for a specific app: make mmig app=authentication)
	@if [ -z "$(app)" ]; then \
		python manage.py makemigrations; \
	else \
		python manage.py makemigrations "$(app)"; \
	fi

mig: ## Apply migrations (optionally for a specific app: make mig app=authentication)
	@if [ -z "$(app)" ]; then \
		python manage.py migrate; \
	else \
		python manage.py migrate "$(app)"; \
	fi

showmig: ## Show migration status for all apps
	python manage.py showmigrations

squash: ## Squash migrations for an app (usage: make squash app=authentication start=0001)
	python manage.py squashmigrations $(app) $(start)

db-reset: ## ⚠️  Reset SQLite database (destructive — dev only)
	@echo "$(RED)⚠  Resetting database...$(NC)"
	rm -f db.sqlite3
	python manage.py makemigrations
	python manage.py migrate
	@echo "$(GREEN)✓ Database reset complete$(NC)"

db-shell: ## Open database shell (dbshell)
	python manage.py dbshell

# ═══════════════════════════════════════════════════════════════
##@ Admin & Users
# ═══════════════════════════════════════════════════════════════

superuser: ## Create a Django superuser
	python manage.py createsuperuser

changepass: ## Change a user's password
	python manage.py changepassword

static: ## Collect static files
	@echo "$(CYAN)Collecting static files...$(NC)"
	python manage.py collectstatic --noinput
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

celery: ## Start Celery worker (general queue)
	@echo "$(CYAN)Starting Celery worker...$(NC)"
	celery -A backend worker --loglevel=info --concurrency=4

celery-emails: ## Start Celery worker for email queue
	celery -A backend worker -Q emails --loglevel=info --concurrency=2

celery-critical: ## Start Celery worker for critical queue
	celery -A backend worker -Q critical --loglevel=info --concurrency=2

celery-analytics: ## Start Celery worker for analytics queue
	celery -A backend worker -Q analytics --loglevel=info --concurrency=1

celery-beat: ## Start Celery Beat scheduler
	celery -A backend beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler

flower: ## Start Flower monitoring dashboard (port 5555)
	@echo "$(CYAN)Starting Flower at http://localhost:5555$(NC)"
	celery -A backend flower --port=5555

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