#!/usr/bin/env bash
# ============================================================
# FASHIONISTAR — cURL Stress Test Suite
# Phase 10: 1000 concurrent requests per critical endpoint
#
# Usage:
#   chmod +x curl_stress.sh
#   BACKEND_URL=http://localhost:8001 ./curl_stress.sh
#   BACKEND_URL=https://your-api.run.app ./curl_stress.sh
#
# Requirements: curl, jq, bc, GNU parallel (optional for parallel mode)
# ============================================================

set -euo pipefail

BACKEND_URL="${BACKEND_URL:-http://localhost:8001}"
CONCURRENCY="${CONCURRENCY:-100}"
REQUESTS_PER_ENDPOINT="${REQUESTS:-1000}"
TIMEOUT_SECS="${TIMEOUT:-10}"
OUTPUT_DIR="${OUTPUT_DIR:-/tmp/fashionistar_stress}"
AUTH_TOKEN="${AUTH_TOKEN:-}"

mkdir -p "$OUTPUT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[PASS]${NC} $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error()   { echo -e "${RED}[FAIL]${NC} $*"; }

# ── Helper: run N concurrent curl requests and report stats ──────────────────
stress_endpoint() {
    local label="$1"
    local method="${2:-GET}"
    local path="$3"
    local body="${4:-}"
    local expected_status="${5:-200}"

    local url="${BACKEND_URL}${path}"
    local out_file="${OUTPUT_DIR}/${label// /_}.log"
    local total=0
    local success=0
    local fail=0
    local total_time=0

    log_info "Stressing: $label ($method $url) — ${REQUESTS_PER_ENDPOINT}req / ${CONCURRENCY}c"

    > "$out_file"

    for i in $(seq 1 "$REQUESTS_PER_ENDPOINT"); do
        {
            local args=(-s -o /dev/null -w "%{http_code} %{time_total}")
            args+=(-m "$TIMEOUT_SECS")
            args+=(-X "$method")
            [[ -n "$AUTH_TOKEN" ]] && args+=(-H "Authorization: Bearer $AUTH_TOKEN")
            args+=(-H "Content-Type: application/json")
            args+=(-H "X-Idempotency-Key: stress-$label-$i-$(date +%s%N)")
            [[ -n "$body" ]] && args+=(--data-raw "$body")
            curl "${args[@]}" "$url" >> "$out_file" 2>&1
            echo >> "$out_file"
        } &

        # Throttle concurrency
        if (( i % CONCURRENCY == 0 )); then
            wait
        fi
    done
    wait

    # Parse results
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        status=$(echo "$line" | awk '{print $1}')
        time=$(echo "$line" | awk '{print $2}')
        total=$((total + 1))
        if [[ "$status" == "$expected_status" ]]; then
            success=$((success + 1))
        else
            fail=$((fail + 1))
        fi
        total_time=$(echo "$total_time + $time" | bc)
    done < "$out_file"

    if [[ $total -eq 0 ]]; then
        log_warn "$label: no results"
        return
    fi

    local avg_time
    avg_time=$(echo "scale=3; $total_time / $total" | bc)
    local success_rate
    success_rate=$(echo "scale=1; $success * 100 / $total" | bc)

    if (( fail == 0 )); then
        log_success "$label: $success/$total (${success_rate}%) avg=${avg_time}s"
    else
        log_error "$label: $success/$total (${success_rate}%) failures=$fail avg=${avg_time}s"
    fi
}

# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS UNDER STRESS
# ══════════════════════════════════════════════════════════════════════════════

log_info "Starting FASHIONISTAR cURL Stress Suite"
log_info "Backend: $BACKEND_URL | Concurrency: $CONCURRENCY | Requests: $REQUESTS_PER_ENDPOINT"
echo ""

# ── P0: Health Check ─────────────────────────────────────────────────────────
stress_endpoint "health-check" GET "/api/v1/health/" "" 200

# ── P0: Auth — Login (rate-limited, use small N) ─────────────────────────────
REQUESTS=50 stress_endpoint "auth-login-invalid" POST "/api/v1/auth/login/" \
  '{"email":"nonexistent@test.com","password":"wrongpass"}' 400

# ── P0: Catalog — Product listing (unauthenticated, high traffic) ─────────────
stress_endpoint "catalog-products-list" GET "/api/v1/ninja/products/" "" 200

# ── P0: Catalog — Category tree ──────────────────────────────────────────────
stress_endpoint "catalog-categories" GET "/api/v1/ninja/categories/" "" 200

# ── P0: Measurements — Profile (authenticated) ───────────────────────────────
[[ -n "$AUTH_TOKEN" ]] && \
  stress_endpoint "measurement-profile" GET "/api/v1/ninja/measurements/profile/" "" 200

# ── P0: Cart — View cart (session-keyed) ─────────────────────────────────────
stress_endpoint "cart-view" GET "/api/v1/ninja/cart/" "" 200

# ── P0: Orders — List (authenticated) ────────────────────────────────────────
[[ -n "$AUTH_TOKEN" ]] && \
  stress_endpoint "orders-list" GET "/api/v1/ninja/orders/" "" 200

# ── P0: Vendor — Product list (authenticated vendor) ─────────────────────────
[[ -n "$AUTH_TOKEN" ]] && \
  stress_endpoint "vendor-products" GET "/api/v1/ninja/vendor/products/" "" 200

# ── P0: Notifications — Feed (authenticated) ─────────────────────────────────
[[ -n "$AUTH_TOKEN" ]] && \
  stress_endpoint "notifications-feed" GET "/api/v1/ninja/notifications/" "" 200

echo ""
log_info "Stress suite complete. Logs saved to: $OUTPUT_DIR"
