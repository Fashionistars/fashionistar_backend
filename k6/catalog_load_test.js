/**
 * k6/catalog_load_test.js
 * FASHIONISTAR — K6 Load Test Campaign
 * Phase 10 / Criterion E: 100k RPS sustained load
 *
 * Stages:
 *   0 → 1k VUs over 2 min   (warm-up)
 *   1k → 10k VUs over 5 min (ramp)
 *   10k → 100k VUs over 10 min (peak)
 *   100k → 0 VUs over 2 min (cool-down)
 *
 * Thresholds:
 *   p95 response time < 100ms
 *   p99 response time < 200ms
 *   Error rate < 0.1%
 *
 * Usage:
 *   k6 run --env API_BASE=https://api.fashionistar.ng k6/catalog_load_test.js
 */

import http from "k6/http";
import { check, group, sleep } from "k6";
import { Rate, Trend, Counter } from "k6/metrics";

// ── Custom metrics ────────────────────────────────────────────────────────────

const errorRate = new Rate("error_rate");
const authLatency = new Trend("auth_latency_ms", true);
const catalogLatency = new Trend("catalog_latency_ms", true);
const orderLatency = new Trend("order_latency_ms", true);
const failedRequests = new Counter("failed_requests");

// ── Configuration ─────────────────────────────────────────────────────────────

const API_BASE = __ENV.API_BASE || "http://localhost:8000";

export const options = {
  stages: [
    { duration: "2m", target: 1_000 },    // Warm-up: 0 → 1k VUs
    { duration: "5m", target: 10_000 },   // Ramp: 1k → 10k VUs
    { duration: "10m", target: 100_000 }, // Peak: 10k → 100k VUs
    { duration: "2m", target: 0 },        // Cool-down
  ],
  thresholds: {
    // SLA targets
    "http_req_duration": ["p(95)<100", "p(99)<200"],
    "http_req_failed": ["rate<0.001"],
    // Custom metrics
    "catalog_latency_ms": ["p(95)<80"],
    "auth_latency_ms": ["p(95)<150"],
    "error_rate": ["rate<0.01"],
  },
  ext: {
    loadimpact: {
      projectID: 0,
      name: "FASHIONISTAR — 100k RPS Campaign",
    },
  },
};

// ── Shared headers ────────────────────────────────────────────────────────────

const HEADERS = {
  "Content-Type": "application/json",
  "Accept": "application/json",
  "X-Load-Test": "1",
};

// ── Auth token cache (per VU, refreshed every 50 iterations) ─────────────────

let _authToken = "";
let _tokenIteration = 0;

function getToken() {
  const iteration = __ITER;
  if (_authToken && iteration - _tokenIteration < 50) return _authToken;

  const res = http.post(
    `${API_BASE}/api/v1/auth/login/`,
    JSON.stringify({
      email: `loadtest+${__VU}@fashionistar.ng`,
      password: "LoadTest!2026",
    }),
    { headers: HEADERS, timeout: "10s" }
  );

  authLatency.add(res.timings.duration);

  if (res.status === 200) {
    try {
      const body = JSON.parse(res.body);
      _authToken = body.access || "";
      _tokenIteration = iteration;
    } catch (_) { /* silent */ }
  }
  return _authToken;
}

// ── Scenario: Anonymous catalog browsing ─────────────────────────────────────

function scenarioCatalog() {
  group("Catalog — Anonymous", () => {
    // Product list (most common request)
    const listRes = http.get(
      `${API_BASE}/api/v1/ninja/products/?page=1&page_size=20`,
      { headers: HEADERS, timeout: "5s" }
    );
    catalogLatency.add(listRes.timings.duration);
    const ok = check(listRes, {
      "product list 200": (r) => r.status === 200,
      "product list < 100ms": (r) => r.timings.duration < 100,
    });
    if (!ok) { errorRate.add(1); failedRequests.add(1); } else { errorRate.add(0); }

    // Featured products
    const featRes = http.get(
      `${API_BASE}/api/v1/ninja/products/?featured=true&page_size=10`,
      { headers: HEADERS, timeout: "5s" }
    );
    catalogLatency.add(featRes.timings.duration);
    check(featRes, { "featured 200": (r) => r.status === 200 });

    // Category tree
    const catRes = http.get(
      `${API_BASE}/api/v1/ninja/catalog/categories/`,
      { headers: HEADERS, timeout: "5s" }
    );
    check(catRes, { "categories 200": (r) => r.status === 200 });

    // Health check (load balancer probe simulation)
    const healthRes = http.get(
      `${API_BASE}/api/v1/health/`,
      { headers: HEADERS, timeout: "3s" }
    );
    check(healthRes, { "health 200": (r) => r.status === 200 });
  });
}

// ── Scenario: Authenticated user flow ────────────────────────────────────────

function scenarioAuthenticated() {
  const token = getToken();
  if (!token) return;

  const authHeaders = { ...HEADERS, "Authorization": `Bearer ${token}` };

  group("Authenticated — User Flow", () => {
    // View cart
    const cartRes = http.get(
      `${API_BASE}/api/v1/ninja/cart/`,
      { headers: authHeaders, timeout: "5s" }
    );
    check(cartRes, { "cart 200": (r) => r.status === 200 });

    // View orders
    const orderRes = http.get(
      `${API_BASE}/api/v1/ninja/orders/?page=1&page_size=10`,
      { headers: authHeaders, timeout: "5s" }
    );
    orderLatency.add(orderRes.timings.duration);
    check(orderRes, {
      "orders 200": (r) => r.status === 200,
      "orders < 150ms": (r) => r.timings.duration < 150,
    });

    // View measurements
    const measRes = http.get(
      `${API_BASE}/api/v1/ninja/measurements/`,
      { headers: authHeaders, timeout: "5s" }
    );
    check(measRes, { "measurements 200": (r) => [200, 404].includes(r.status) });
  });
}

// ── Main VU entrypoint ────────────────────────────────────────────────────────

export default function () {
  // 70% anonymous catalog traffic, 30% authenticated
  if (Math.random() < 0.7) {
    scenarioCatalog();
  } else {
    scenarioAuthenticated();
  }

  // Realistic think time: 0.1–0.5s between requests
  sleep(Math.random() * 0.4 + 0.1);
}

// ── Summary report ────────────────────────────────────────────────────────────

export function handleSummary(data) {
  return {
    "k6/reports/load_test_summary.json": JSON.stringify(data, null, 2),
    "k6/reports/load_test_summary.txt": textSummary(data),
    stdout: textSummary(data, { indent: " ", enableColors: true }),
  };
}

function textSummary(data, opts = {}) {
  const indent = opts.indent || "";
  const lines = [
    `${indent}FASHIONISTAR Load Test Summary`,
    `${indent}==============================`,
    `${indent}Duration: ${data.state?.testRunDurationMs ?? 0}ms`,
    `${indent}VUs Max: ${data.metrics?.vus_max?.values?.max ?? 0}`,
    `${indent}Requests: ${data.metrics?.http_reqs?.values?.count ?? 0}`,
    `${indent}RPS: ${(data.metrics?.http_reqs?.values?.rate ?? 0).toFixed(0)}`,
    `${indent}p95 latency: ${(data.metrics?.http_req_duration?.values?.["p(95)"] ?? 0).toFixed(2)}ms`,
    `${indent}p99 latency: ${(data.metrics?.http_req_duration?.values?.["p(99)"] ?? 0).toFixed(2)}ms`,
    `${indent}Error rate: ${((data.metrics?.http_req_failed?.values?.rate ?? 0) * 100).toFixed(3)}%`,
  ];
  return lines.join("\n");
}
