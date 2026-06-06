#!/usr/bin/env bash
# ======================================================================
# FASHIONISTAR — cURL Stress Test Suite
# Phase 10 / Criterion A: 1000 concurrent requests per critical endpoint
# ======================================================================
# Requirements: curl, xargs (GNU coreutils)
# Usage:
#   chmod +x curl_stress.sh
#   ./curl_stress.sh https://api.fashionistar.ng 1000
#
# Reports: success count, failure count, avg latency per endpoint
# ======================================================================

set -euo pipefail

API_BASE="${1:-http://localhost:8000}"
CONCURRENCY="${2:-1000}"
REPORT_DIR="$(dirname "$0")/reports"
mkdir -p "$REPORT_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REPORT="$REPORT_DIR/curl_stress_${TIMESTAMP}.txt"

echo "=====================================================" | tee -a "$REPORT"
echo "FASHIONISTAR cURL Stress Test — $(date)"              | tee -a "$REPORT"
echo "API Base: $API_BASE"                                   | tee -a "$REPORT"
echo "Concurrency: $CONCURRENCY requests per endpoint"       | tee -a "$REPORT"
echo "=====================================================" | tee -a "$REPORT"

# ── Helper: single timed request ────────────────────────────────────────────
run_request() {
  local url="$1"
  local method="${2:-GET}"
  local body="${3:-}"
  local token="${4:-}"

  local headers=("-H" "Content-Type: application/json" "-H" "Accept: application/json")
  if [[ -n "$token" ]]; then
    headers+=("-H" "Authorization: Bearer $token")
  fi

  local start_ns
  start_ns=$(date +%s%N 2>/dev/null || echo 0)

  local http_code
  if [[ "$method" == "POST" && -n "$body" ]]; then
    http_code=$(curl -s -o /dev/null -w "%{http_code}" \
      -X POST "${headers[@]}" \
      -d "$body" \
      --max-time 30 \
      "$url" 2>/dev/null || echo "000")
  else
    http_code=$(curl -s -o /dev/null -w "%{http_code}" \
      "${headers[@]}" \
      --max-time 30 \
      "$url" 2>/dev/null || echo "000")
  fi

  local end_ns
  end_ns=$(date +%s%N 2>/dev/null || echo 0)
  local elapsed_ms=$(( (end_ns - start_ns) / 1000000 ))

  echo "$http_code $elapsed_ms"
}
export -f run_request

# ── Helper: run endpoint stress test ────────────────────────────────────────
stress_endpoint() {
  local name="$1"
  local url="$2"
  local method="${3:-GET}"
  local body="${4:-}"

  echo ""                                                              | tee -a "$REPORT"
  echo "── $name ──────────────────────────────────────────────────" | tee -a "$REPORT"
  echo "   URL: $url"                                                 | tee -a "$REPORT"
  echo "   Method: $method | Concurrency: $CONCURRENCY"              | tee -a "$REPORT"

  local results
  results=$(seq 1 "$CONCURRENCY" | xargs -P "$CONCURRENCY" -I{} bash -c "run_request '$url' '$method' '$body'")

  local total=0
  local success=0
  local fail=0
  local total_ms=0

  while IFS=' ' read -r code ms; do
    total=$((total + 1))
    total_ms=$((total_ms + ms))
    if [[ "$code" =~ ^2 ]]; then
      success=$((success + 1))
    else
      fail=$((fail + 1))
    fi
  done <<< "$results"

  local avg_ms=0
  [[ $total -gt 0 ]] && avg_ms=$((total_ms / total))

  echo "   ✅ Success: $success / $total"  | tee -a "$REPORT"
  echo "   ❌ Failed:  $fail / $total"     | tee -a "$REPORT"
  echo "   ⏱️  Avg Latency: ${avg_ms}ms"   | tee -a "$REPORT"

  # FAIL if <95% success rate
  local success_pct=0
  [[ $total -gt 0 ]] && success_pct=$((success * 100 / total))
  if [[ $success_pct -lt 95 ]]; then
    echo "   ⚠️  WARN: Success rate ${success_pct}% < 95% threshold" | tee -a "$REPORT"
  fi
}

# ── Critical Endpoints ───────────────────────────────────────────────────────
echo ""
echo "Starting stress tests…"

# Public catalog (no auth)
stress_endpoint "Product List"       "$API_BASE/api/v1/catalog/products/"          "GET"
stress_endpoint "Featured Products"  "$API_BASE/api/v1/catalog/products/featured/" "GET"
stress_endpoint "Health Check"       "$API_BASE/api/v1/health/"                    "GET"
stress_endpoint "Category Tree"      "$API_BASE/api/v1/catalog/categories/"        "GET"

# Auth endpoints
LOGIN_BODY='{"email":"stress@test.fashionistar.ng","password":"StressTest!2026"}'
stress_endpoint "Auth Login"         "$API_BASE/api/v1/auth/login/"                "POST" "$LOGIN_BODY"
stress_endpoint "Token Refresh"      "$API_BASE/api/v1/auth/token/refresh/"        "POST" '{"refresh":""}'

echo ""
echo "=====================================================" | tee -a "$REPORT"
echo "✅ Stress test complete. Report: $REPORT"              | tee -a "$REPORT"
echo "=====================================================" | tee -a "$REPORT"
