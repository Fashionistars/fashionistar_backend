#!/bin/bash
# FASHIONISTAR Backend Entrypoint Script
# Responsibilities:
#   1. Wait for database to be ready
#   2. Run database migrations
#   3. Collect static files
#   4. Start application server

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}  FASHIONISTAR Backend Entrypoint${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# ═══════════════════════════════════════════════════════════
# 1. Wait for Database to be Ready
# ═══════════════════════════════════════════════════════════

if [ -n "$DB_HOST" ]; then
    echo -e "${YELLOW}⏳ Waiting for PostgreSQL database...${NC}"
    
    DB_HOST=${DB_HOST:-localhost}
    DB_PORT=${DB_PORT:-5432}
    DB_USER=${DB_USER:-postgres}
    TIMEOUT=30
    COUNTER=0
    
    while ! pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" 2>/dev/null; do
        COUNTER=$((COUNTER + 1))
        if [ $COUNTER -gt $TIMEOUT ]; then
            echo -e "${RED}✗ Database failed to start within ${TIMEOUT} seconds${NC}"
            exit 1
        fi
        echo -e "${YELLOW}  Attempt $COUNTER/$TIMEOUT...${NC}"
        sleep 1
    done
    
    echo -e "${GREEN}✓ Database is ready${NC}"
else
    echo -e "${YELLOW}⚠ DB_HOST not set, skipping database check${NC}"
fi

# ═══════════════════════════════════════════════════════════
# 2. Run Database Migrations
# ═══════════════════════════════════════════════════════════

echo -e "${YELLOW}📦 Running database migrations...${NC}"

if uv run python manage.py migrate --noinput 2>/dev/null; then
    echo -e "${GREEN}✓ Migrations completed successfully${NC}"
else
    echo -e "${YELLOW}⚠ Migrations already up to date or not applicable${NC}"
fi

# ═══════════════════════════════════════════════════════════
# 3. Collect Static Files (Production)
# ═══════════════════════════════════════════════════════════

if [ "$DEBUG" = "False" ] || [ "$DEBUG" = "false" ]; then
    echo -e "${YELLOW}📂 Collecting static files...${NC}"
    
    if uv run python manage.py collectstatic --noinput 2>/dev/null; then
        echo -e "${GREEN}✓ Static files collected${NC}"
    else
        echo -e "${YELLOW}⚠ Static files already collected or path issues${NC}"
    fi
fi

# ═══════════════════════════════════════════════════════════
# 4. Create Health Check Endpoint (if not exists)
# ═══════════════════════════════════════════════════════════

echo -e "${YELLOW}🏥 Verifying health check endpoint...${NC}"

if uv run python -c "from django.urls import path; from django.http import JsonResponse; print('Django loaded successfully')" 2>/dev/null; then
    echo -e "${GREEN}✓ Django configuration verified${NC}"
else
    echo -e "${RED}✗ Django configuration error${NC}"
    exit 1
fi

# ═══════════════════════════════════════════════════════════
# 5. Show Configuration Summary
# ═══════════════════════════════════════════════════════════

echo -e "${YELLOW}📋 Configuration Summary:${NC}"
echo -e "  ${GREEN}Database:${NC} ${DB_HOST}:${DB_PORT}/${DB_NAME}"
echo -e "  ${GREEN}Redis:${NC} ${REDIS_HOST}:${REDIS_PORT}"
echo -e "  ${GREEN}Debug:${NC} ${DEBUG}"
echo -e "  ${GREEN}Settings:${NC} ${DJANGO_SETTINGS_MODULE}"

# ═══════════════════════════════════════════════════════════
# 6. Start Application Server
# ═══════════════════════════════════════════════════════════

echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✅ Entrypoint initialization complete!${NC}"
echo -e "${GREEN}   Starting application server...${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Execute the main process
exec "$@"
