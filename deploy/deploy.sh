#!/usr/bin/env bash
# ============================================================================
# FASHIONISTAR — Production Deployment Script (Oracle Cloud)
# ============================================================================
# Run this from your local machine OR from GitHub Actions
#
# Usage:
#   ./deploy/deploy.sh            # Full deploy (pull, migrate, restart)
#   ./deploy/deploy.sh --migrate-only  # Only run migrations
#   ./deploy/deploy.sh --health   # Only run health check
# ============================================================================

set -euo pipefail

ORACLE_HOST="${ORACLE_HOST:-}"
ORACLE_SSH_KEY="${ORACLE_SSH_KEY_PATH:-~/.ssh/oracle_fashionistar}"
APP_DIR="/home/ubuntu/fashionistar_backend"
COMPOSE_FILE="docker-compose.production.yml"
API_URL="https://api.fashionistar.net"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ── Validate environment ───────────────────────────────────────────────────────
if [ -z "$ORACLE_HOST" ]; then
    log_error "ORACLE_HOST environment variable is required (export ORACLE_HOST=<your-oracle-ip>)"
fi

SSH_CMD="ssh -i $ORACLE_SSH_KEY -o StrictHostKeyChecking=no ubuntu@$ORACLE_HOST"

# ── Health check function ──────────────────────────────────────────────────────
health_check() {
    log_info "Running health check on $API_URL..."
    for i in 1 2 3 4 5; do
        if curl -fsS --max-time 10 "$API_URL/health/" > /dev/null 2>&1; then
            log_success "Health check passed! ✅"
            return 0
        fi
        log_warn "Health check attempt $i/5 failed, waiting 10s..."
        sleep 10
    done
    log_error "Health check failed after 5 attempts ❌"
}

# ── Handle flags ───────────────────────────────────────────────────────────────
case "${1:-}" in
    --health)
        health_check
        exit 0
        ;;
    --migrate-only)
        log_info "Running migrations only..."
        $SSH_CMD "cd $APP_DIR && docker compose -f $COMPOSE_FILE exec -T api python manage.py migrate --settings=backend.config.production --no-input"
        log_success "Migrations complete"
        exit 0
        ;;
esac

# ── Full Deploy ────────────────────────────────────────────────────────────────
echo ""
echo "======================================================"
echo "  🚀 FASHIONISTAR Production Deploy"
echo "  Target: Oracle Cloud VM ($ORACLE_HOST)"
echo "======================================================"
echo ""

# Get current git SHA
GIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
log_info "Deploying commit: $GIT_SHA"

$SSH_CMD << EOF
set -e
echo "📦 Deploying on Oracle Cloud VM..."
cd $APP_DIR

# Pull latest code
git pull origin main
echo "✅ Code updated to $(git rev-parse --short HEAD)"

# Pull latest Docker images
docker compose -f $COMPOSE_FILE pull api

# Rolling update — restart api service with zero downtime
docker compose -f $COMPOSE_FILE up -d --no-deps api
echo "✅ API container updated"

# Database migrations
docker compose -f $COMPOSE_FILE exec -T api \
    python manage.py migrate --settings=backend.config.production --no-input
echo "✅ Migrations applied"

# Collect static files
docker compose -f $COMPOSE_FILE exec -T api \
    python manage.py collectstatic --noinput --settings=backend.config.production
echo "✅ Static files collected"

# Prune old images
docker image prune -f > /dev/null 2>&1 || true

echo ""
echo "Container status:"
docker compose -f $COMPOSE_FILE ps
EOF

log_success "Remote deployment complete"
sleep 15
health_check

echo ""
echo "======================================================"
echo "  ✅ FASHIONISTAR Deployment Successful!"
echo "  🌐 API: $API_URL"
echo "======================================================"
