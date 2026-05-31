/**
 * tests/k6/catalog_search.js
 *
 * K6 Load Test — FASHIONISTAR Catalog Search
 * Target: GET /api/v1/ninja/catalog/search/?q={query}
 *
 * Tests concurrent search traffic with realistic query variety.
 * Validates latency, response shape, and cache effectiveness (30s TTL).
 *
 * Stages:
 *   0 → 200 VUs  in 30s  (ramp-up)
 *   200 VUs      for 90s  (sustained search load)
 *   200 → 500 VUs in 60s (stress peak)
 *   500 → 0 VUs  in 30s  (ramp-down)
 *
 * Run:
 *   k6 run tests/k6/catalog_search.js
 *   k6 run -e BASE_URL=https://api.fashionistar.net tests/k6/catalog_search.js
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Rate, Trend } from "k6/metrics";
import { randomItem } from "https://jslib.k6.io/k6-utils/1.4.0/index.js";

// ── Custom metrics ─────────────────────────────────────────────────────────────
const searchErrors = new Counter("search_errors");
const searchResultsFound = new Rate("search_results_found_rate");
const searchLatency = new Trend("search_latency_ms");
const searchEmptyQuery = new Rate("search_empty_query_rate");

// ── Config ─────────────────────────────────────────────────────────────────────
const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const SEARCH_BASE = `${BASE_URL}/api/v1/ninja/catalog/search/`;
const BANNERS_URL = `${BASE_URL}/api/v1/ninja/catalog/homepage/banners/?slot=hero`;
const TAGS_URL = `${BASE_URL}/api/v1/ninja/catalog/tags/`;

// Realistic search queries representing Nigerian fashion shoppers
const SEARCH_QUERIES = [
  "senator", "agbada", "gown", "ankara", "lace",
  "kaftan", "aso-ebi", "corporate", "casual", "wedding",
  "fabric", "tailor", "bespoke", "fashion", "dress",
  "suit", "native", "owanbe", "embroidered", "luxury",
];

// Edge cases to stress-test
const EDGE_QUERIES = [
  "a",        // too short — should not hit DB (backend short-circuits < 2 chars)
  "   ",      // whitespace — handled by backend strip
  "非常に良い",  // unicode
  "x".repeat(80), // very long
];

// ── Test options ───────────────────────────────────────────────────────────────
export const options = {
  stages: [
    { duration: "30s", target: 200 },
    { duration: "90s", target: 200 },
    { duration: "60s", target: 500 },
    { duration: "30s", target: 0 },
  ],
  thresholds: {
    http_req_duration: ["p(95)<100", "p(99)<300"],
    http_req_failed: ["rate<0.01"],
    search_latency_ms: ["p(95)<100"],
    // At least 60% of real queries (not edge cases) should return ≥1 result
    search_results_found_rate: ["rate>0.6"],
  },
};

const HEADERS = {
  Accept: "application/json",
  "Content-Type": "application/json",
};

// ── Helpers ────────────────────────────────────────────────────────────────────

function countTotalResults(body) {
  try {
    const d = JSON.parse(body);
    return (
      (d.categories?.length || 0) +
      (d.brands?.length || 0) +
      (d.collections?.length || 0)
    );
  } catch (_) {
    return 0;
  }
}

// ── Main scenario ──────────────────────────────────────────────────────────────

export default function () {
  // 90% real queries, 10% edge cases
  const isEdge = Math.random() < 0.1;
  const q = isEdge
    ? randomItem(EDGE_QUERIES)
    : randomItem(SEARCH_QUERIES);

  const url = `${SEARCH_BASE}?q=${encodeURIComponent(q)}`;
  const start = Date.now();

  const res = http.get(url, { headers: HEADERS });
  const latencyMs = Date.now() - start;
  searchLatency.add(latencyMs);

  const ok = check(res, {
    "search: status 200": (r) => r.status === 200,
    "search: json content-type": (r) =>
      (r.headers["Content-Type"] || "").includes("application/json"),
    "search: valid shape": (r) => {
      try {
        const d = JSON.parse(r.body);
        return (
          Array.isArray(d.categories) &&
          Array.isArray(d.brands) &&
          Array.isArray(d.collections)
        );
      } catch (_) {
        return false;
      }
    },
    "search: latency < 100ms": () => latencyMs < 100,
  });

  if (!ok) searchErrors.add(1);

  // Track result rate only for real queries (edge cases legitimately return 0)
  if (!isEdge && q.trim().length >= 2) {
    const count = countTotalResults(res.body);
    searchResultsFound.add(count > 0 ? 1 : 0);
  }

  // ── Secondary: banners + tags (5% of VUs) ─────────────────────────────────
  if (Math.random() < 0.05) {
    const bannersRes = http.get(BANNERS_URL, { headers: HEADERS });
    check(bannersRes, {
      "banners: status 200": (r) => r.status === 200,
    });
  }

  if (Math.random() < 0.05) {
    const tagsRes = http.get(TAGS_URL, { headers: HEADERS });
    check(tagsRes, {
      "tags: status 200": (r) => r.status === 200,
    });
  }

  // Shorter think time for search (users type quickly)
  sleep(0.2 + Math.random() * 0.8);
}

export function setup() {
  // Pre-warm common search terms into 30s cache
  SEARCH_QUERIES.slice(0, 5).forEach((q) => {
    http.get(`${SEARCH_BASE}?q=${encodeURIComponent(q)}`, { headers: HEADERS });
  });
  console.log("[Setup] Search cache warmed for 5 common terms");
  return { baseUrl: BASE_URL };
}

export function teardown(data) {
  console.log(`[Teardown] Catalog search load test complete. Base: ${data.baseUrl}`);
}
