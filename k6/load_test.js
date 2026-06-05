// k6/load_test.js
// =============================================================
// FASHIONISTAR — Phase 10: K6 Enterprise Load Test
// Target: p95 < 100ms at 10k RPS | 100k VU campaign
//
// Run:
//   k6 run --env BASE_URL=http://localhost:8001 k6/load_test.js
//   k6 run --env BASE_URL=https://api.fashionistar.com \
//          --out json=results/load_test_$(date +%Y%m%d_%H%M%S).json \
//          k6/load_test.js
//
// Environment variables:
//   BASE_URL     — API base URL (required)
//   AUTH_TOKEN   — Bearer token for authenticated scenarios
//   SCENARIO     — 'smoke' | 'load' | 'stress' | 'spike' | 'soak' (default: load)
// =============================================================

import http from "k6/http";
import { check, sleep, group } from "k6";
import { Counter, Rate, Trend } from "k6/metrics";
import { randomItem, randomIntBetween } from "https://jslib.k6.io/k6-utils/1.4.0/index.js";

// ── Custom Metrics ────────────────────────────────────────────────────────────
const errorRate = new Rate("error_rate");
const p95Latency = new Trend("p95_latency_ms", true);
const cartAddDuration = new Trend("cart_add_duration_ms", true);
const catalogPageDuration = new Trend("catalog_page_duration_ms", true);
const authLoginDuration = new Trend("auth_login_duration_ms", true);

// ── Configuration ─────────────────────────────────────────────────────────────
const BASE_URL = __ENV.BASE_URL || "http://localhost:8001";
const AUTH_TOKEN = __ENV.AUTH_TOKEN || "";
const SCENARIO = __ENV.SCENARIO || "load";

// ── Thresholds (FASHIONISTAR SLAs) ────────────────────────────────────────────
export let options = {
  thresholds: {
    // Core SLA: p95 under 100ms
    "http_req_duration": ["p(95)<100", "p(99)<200"],
    // Error budget: less than 0.1% failures
    "http_req_failed": ["rate<0.001"],
    "error_rate": ["rate<0.001"],
    // Domain-specific latencies
    "catalog_page_duration_ms": ["p(95)<80"],
    "cart_add_duration_ms": ["p(95)<150"],
    "auth_login_duration_ms": ["p(95)<200"],
  },

  scenarios: {
    // ── 1. Smoke: verify baseline correctness (1 VU, 1 min) ─────────────────
    smoke: {
      executor: "constant-vus",
      vus: 1,
      duration: "1m",
      gracefulStop: "10s",
      tags: { scenario: "smoke" },
    },

    // ── 2. Load: realistic traffic (ramp to 10k RPS) ─────────────────────────
    load: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "2m", target: 100 },
        { duration: "5m", target: 1000 },
        { duration: "10m", target: 5000 },
        { duration: "5m", target: 10000 },
        { duration: "2m", target: 0 },
      ],
      gracefulRampDown: "30s",
      tags: { scenario: "load" },
    },

    // ── 3. Stress: beyond normal capacity (up to 100k VUs) ───────────────────
    stress: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "2m", target: 1000 },
        { duration: "5m", target: 10000 },
        { duration: "10m", target: 100000 },
        { duration: "2m", target: 0 },
      ],
      gracefulRampDown: "60s",
      tags: { scenario: "stress" },
    },

    // ── 4. Spike: sudden traffic surge ───────────────────────────────────────
    spike: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "30s", target: 100 },
        { duration: "10s", target: 50000 },  // spike
        { duration: "3m", target: 50000 },   // hold spike
        { duration: "30s", target: 0 },
      ],
      tags: { scenario: "spike" },
    },

    // ── 5. Soak: extended endurance (8 hours at 5k VUs) ──────────────────────
    soak: {
      executor: "constant-vus",
      vus: 5000,
      duration: "8h",
      gracefulStop: "2m",
      tags: { scenario: "soak" },
    },
  },
};

// Only run the selected scenario
if (SCENARIO !== "all") {
  const selectedScenario = options.scenarios[SCENARIO];
  if (selectedScenario) {
    options.scenarios = { [SCENARIO]: selectedScenario };
  }
}

// ── Headers ───────────────────────────────────────────────────────────────────
function getHeaders(authenticated = false) {
  const headers = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "X-Idempotency-Key": `k6-${Date.now()}-${Math.random()}`,
  };
  if (authenticated && AUTH_TOKEN) {
    headers["Authorization"] = `Bearer ${AUTH_TOKEN}`;
  }
  return headers;
}

// ── Test Data ─────────────────────────────────────────────────────────────────
const CATALOG_PAGES = [1, 2, 3, 4, 5];
const SEARCH_QUERIES = ["ankara", "aso ebi", "kaftan", "agbada", "buba", "suit"];
const CATEGORIES = ["women", "men", "children", "accessories", "fabric"];

// ── Scenario Functions ────────────────────────────────────────────────────────

function scenarioHealthCheck() {
  const res = http.get(`${BASE_URL}/api/v1/health/`, { headers: getHeaders() });
  check(res, {
    "health: status 200": (r) => r.status === 200,
    "health: response < 50ms": (r) => r.timings.duration < 50,
  });
  errorRate.add(res.status !== 200);
}

function scenarioCatalogBrowse() {
  group("Catalog Browse", () => {
    // Product list
    const page = randomItem(CATALOG_PAGES);
    const res = http.get(
      `${BASE_URL}/api/v1/ninja/products/?page=${page}&page_size=20`,
      { headers: getHeaders() }
    );
    catalogPageDuration.add(res.timings.duration);
    check(res, {
      "catalog: status 200": (r) => r.status === 200,
      "catalog: has results": (r) => {
        try { return JSON.parse(r.body).data?.count > 0; } catch { return false; }
      },
    });
    errorRate.add(res.status !== 200);

    sleep(randomIntBetween(1, 3) * 0.1);

    // Category filter
    const cat = randomItem(CATEGORIES);
    const catRes = http.get(
      `${BASE_URL}/api/v1/ninja/products/?category=${cat}&page=1`,
      { headers: getHeaders() }
    );
    check(catRes, { "category filter: status 200": (r) => r.status === 200 });
    errorRate.add(catRes.status !== 200);
  });
}

function scenarioSearch() {
  const query = randomItem(SEARCH_QUERIES);
  const res = http.get(
    `${BASE_URL}/api/v1/ninja/products/search/?q=${encodeURIComponent(query)}`,
    { headers: getHeaders() }
  );
  check(res, {
    "search: status 200 or 404": (r) => [200, 404].includes(r.status),
  });
  errorRate.add(![200, 404].includes(res.status));
}

function scenarioCartOperation() {
  if (!AUTH_TOKEN) return;

  group("Cart Operations", () => {
    // View cart
    const cartRes = http.get(
      `${BASE_URL}/api/v1/ninja/cart/`,
      { headers: getHeaders(true) }
    );
    check(cartRes, { "cart view: status 200": (r) => r.status === 200 });

    sleep(0.05);

    // Get a product to add
    const productsRes = http.get(
      `${BASE_URL}/api/v1/ninja/products/?page=1&page_size=1`,
      { headers: getHeaders() }
    );
    if (productsRes.status === 200) {
      try {
        const data = JSON.parse(productsRes.body);
        const product = data?.data?.results?.[0];
        if (product?.id) {
          const addRes = http.post(
            `${BASE_URL}/api/v1/cart/add/`,
            JSON.stringify({ product_id: product.id, quantity: 1 }),
            { headers: getHeaders(true) }
          );
          cartAddDuration.add(addRes.timings.duration);
          check(addRes, {
            "cart add: status 2xx": (r) => r.status >= 200 && r.status < 300,
          });
          errorRate.add(addRes.status >= 400);
        }
      } catch {}
    }
  });
}

function scenarioNotificationFeed() {
  if (!AUTH_TOKEN) return;

  const res = http.get(
    `${BASE_URL}/api/v1/ninja/notifications/?page=1&page_size=10`,
    { headers: getHeaders(true) }
  );
  check(res, { "notifications: status 200": (r) => r.status === 200 });
  errorRate.add(res.status !== 200);
}

// ── Main VU Function ──────────────────────────────────────────────────────────

export default function () {
  // Distribution: 60% catalog, 20% search, 10% cart, 5% notifications, 5% health
  const rand = Math.random();

  if (rand < 0.05) {
    scenarioHealthCheck();
  } else if (rand < 0.25) {
    scenarioSearch();
  } else if (rand < 0.35) {
    scenarioCartOperation();
  } else if (rand < 0.40) {
    scenarioNotificationFeed();
  } else {
    scenarioCatalogBrowse();
  }

  sleep(randomIntBetween(1, 3) * 0.05);
}

// ── Setup & Teardown ──────────────────────────────────────────────────────────

export function setup() {
  const res = http.get(`${BASE_URL}/api/v1/health/`);
  if (res.status !== 200) {
    throw new Error(`Backend health check failed: ${res.status}. Aborting load test.`);
  }
  console.log(`Load test starting against: ${BASE_URL}`);
  return { started_at: new Date().toISOString() };
}

export function teardown(data) {
  console.log(`Load test completed. Started: ${data.started_at}`);
}

// ── Summary Report ────────────────────────────────────────────────────────────

export function handleSummary(data) {
  const p95 = data.metrics["http_req_duration"]?.values?.["p(95)"] || 0;
  const errRate = data.metrics["http_req_failed"]?.values?.rate || 0;
  const reqCount = data.metrics["http_reqs"]?.values?.count || 0;

  const report = {
    summary: {
      total_requests: reqCount,
      p95_latency_ms: p95.toFixed(2),
      error_rate_pct: (errRate * 100).toFixed(3),
      sla_p95_passed: p95 < 100,
      sla_error_rate_passed: errRate < 0.001,
      scenario: SCENARIO,
      base_url: BASE_URL,
      timestamp: new Date().toISOString(),
    },
    raw: data,
  };

  return {
    "results/k6_summary.json": JSON.stringify(report, null, 2),
    stdout: `
╔══════════════════════════════════════════════╗
║     FASHIONISTAR K6 Load Test Summary        ║
╠══════════════════════════════════════════════╣
║  Scenario:       ${SCENARIO.padEnd(27)}║
║  Base URL:       ${BASE_URL.substring(0, 27).padEnd(27)}║
║  Total Requests: ${String(reqCount).padEnd(27)}║
║  p95 Latency:    ${(p95.toFixed(2) + "ms").padEnd(27)}║
║  Error Rate:     ${((errRate * 100).toFixed(3) + "%").padEnd(27)}║
║  SLA p95 < 100ms: ${(p95 < 100 ? "✅ PASS" : "❌ FAIL").padEnd(26)}║
║  SLA err < 0.1%:  ${(errRate < 0.001 ? "✅ PASS" : "❌ FAIL").padEnd(26)}║
╚══════════════════════════════════════════════╝
`,
  };
}
