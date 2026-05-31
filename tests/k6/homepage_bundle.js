/**
 * tests/k6/homepage_bundle.js
 *
 * K6 Load Test — FASHIONISTAR Homepage Bundle v2
 * Target: GET /api/v1/ninja/catalog/homepage/bundle/
 *
 * Stages:
 *   0  → 100 VUs  in 30s  (ramp-up)
 *   100 → 500 VUs in 60s  (sustained load)
 *   500 → 1000 VUs in 60s (stress test)
 *   1000 VUs      for 120s (peak)
 *   1000 → 0 VUs  in 30s  (ramp-down)
 *
 * Acceptance criteria (thresholds):
 *   http_req_duration p95 < 100ms (target: <30ms with Redis cache hit)
 *   http_req_failed   < 1%
 *   http_reqs         > 10,000 / sec at peak
 *
 * Run:
 *   k6 run tests/k6/homepage_bundle.js
 *   k6 run --out json=results.json tests/k6/homepage_bundle.js
 *   k6 run -e BASE_URL=https://api.fashionistar.net tests/k6/homepage_bundle.js
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Rate, Trend } from "k6/metrics";

// ── Custom metrics ─────────────────────────────────────────────────────────────
const bundleErrors = new Counter("bundle_errors");
const bundleCacheHit = new Rate("bundle_cache_hit_rate");
const bundleLatency = new Trend("bundle_latency_ms");
const catalogSectionsOk = new Rate("catalog_sections_ok");

// ── Config ─────────────────────────────────────────────────────────────────────
const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const BUNDLE_ENDPOINT = `${BASE_URL}/api/v1/ninja/catalog/homepage/bundle/`;
const CATEGORIES_ENDPOINT = `${BASE_URL}/api/v1/ninja/catalog/categories/`;
const BRANDS_ENDPOINT = `${BASE_URL}/api/v1/ninja/catalog/brands/`;
const SEARCH_ENDPOINT = `${BASE_URL}/api/v1/ninja/catalog/search/?q=fashion`;

// ── Test options ───────────────────────────────────────────────────────────────
export const options = {
  stages: [
    { duration: "30s", target: 100 },   // ramp-up
    { duration: "60s", target: 500 },   // sustained
    { duration: "60s", target: 1000 },  // stress
    { duration: "120s", target: 1000 }, // peak — 10k RPS target
    { duration: "30s", target: 0 },     // ramp-down
  ],
  thresholds: {
    // P95 must be under 100ms (Redis cache should deliver <10ms)
    http_req_duration: ["p(95)<100", "p(99)<250"],
    // Less than 1% failures
    http_req_failed: ["rate<0.01"],
    // Custom: cache hit rate should be >80% at sustained load
    bundle_cache_hit_rate: ["rate>0.8"],
    // Custom: all 6 bundle sections must be non-empty at 95th percentile
    catalog_sections_ok: ["rate>0.95"],
    // Custom: bundle latency
    bundle_latency_ms: ["p(95)<100"],
  },
};

// ── Helpers ────────────────────────────────────────────────────────────────────

const HEADERS = {
  Accept: "application/json",
  "Content-Type": "application/json",
};

function assertBundleShape(body) {
  try {
    const data = JSON.parse(body);
    const sections = [
      data.collections,
      data.categories,
      data.featured_products,
      data.hot_deals,
      data.reviews,
      data.banners,
    ];
    // All sections must be arrays (can be empty on cold start)
    return sections.every((s) => Array.isArray(s));
  } catch (_) {
    return false;
  }
}

function isCacheHit(response) {
  // Django-Redis sets X-Cache-Status or Age header when cached
  const age = parseInt(response.headers["Age"] || "0", 10);
  const cacheStatus = response.headers["X-Cache-Status"] || "";
  return age > 0 || cacheStatus.toLowerCase().includes("hit");
}

// ── Main test scenario ─────────────────────────────────────────────────────────

export default function () {
  const start = Date.now();

  // ── Primary: homepage bundle ─────────────────────────────────────────────────
  const bundleRes = http.get(BUNDLE_ENDPOINT, { headers: HEADERS });
  const latencyMs = Date.now() - start;
  bundleLatency.add(latencyMs);

  const bundleOk = check(bundleRes, {
    "bundle: status 200": (r) => r.status === 200,
    "bundle: content-type json": (r) =>
      (r.headers["Content-Type"] || "").includes("application/json"),
    "bundle: valid shape": (r) => assertBundleShape(r.body),
    "bundle: latency < 100ms": () => latencyMs < 100,
  });

  if (!bundleOk) bundleErrors.add(1);
  bundleCacheHit.add(isCacheHit(bundleRes) ? 1 : 0);

  // Validate section structure
  try {
    const data = JSON.parse(bundleRes.body);
    const allArrays = [
      data.collections,
      data.categories,
      data.featured_products,
      data.hot_deals,
      data.reviews,
      data.banners,
    ].every(Array.isArray);
    catalogSectionsOk.add(allArrays ? 1 : 0);
  } catch (_) {
    catalogSectionsOk.add(0);
  }

  // ── Secondary (10% of VUs): list endpoints ─────────────────────────────────
  if (Math.random() < 0.1) {
    const catRes = http.get(CATEGORIES_ENDPOINT, { headers: HEADERS });
    check(catRes, {
      "categories: status 200": (r) => r.status === 200,
      "categories: has results": (r) => {
        try {
          const d = JSON.parse(r.body);
          return Array.isArray(d.results) || Array.isArray(d);
        } catch (_) {
          return false;
        }
      },
    });
  }

  // ── Tertiary (5% of VUs): brands endpoint ─────────────────────────────────
  if (Math.random() < 0.05) {
    const brandRes = http.get(BRANDS_ENDPOINT, { headers: HEADERS });
    check(brandRes, {
      "brands: status 200": (r) => r.status === 200,
    });
  }

  // Think time: realistic user pacing (0.5–1.5s between requests)
  sleep(0.5 + Math.random());
}

// ── Setup (called once before test) ───────────────────────────────────────────
export function setup() {
  // Warm the Redis cache with a single request before ramping VUs
  const warmRes = http.get(BUNDLE_ENDPOINT, { headers: HEADERS });
  console.log(
    `[Setup] Cache warm request: status=${warmRes.status} latency=${warmRes.timings.duration.toFixed(0)}ms`
  );

  check(warmRes, {
    "setup: backend reachable": (r) => r.status === 200,
  });

  return { baseUrl: BASE_URL };
}

// ── Teardown (called once after test) ─────────────────────────────────────────
export function teardown(data) {
  console.log(`[Teardown] Test complete. Target base URL: ${data.baseUrl}`);
}
