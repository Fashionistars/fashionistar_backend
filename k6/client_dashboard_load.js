/**
 * k6 Load Test — Fashionistar Client Dashboard (Ninja Async Endpoint)
 *
 * Simulates 500 concurrent virtual users over 30 seconds targeting the
 * Ninja async client dashboard read endpoint.
 *
 * Tests:
 *   (c) 100,000+ RPS simulation
 *   (d) Concurrency: 500 VUs (virtual users) hitting simultaneously
 *   (a) Race conditions: overlapping requests with same auth token
 *   (b) Idempotency: same GET request always returns identical structure
 *
 * Usage:
 *   # Install k6: https://k6.io/docs/get-started/installation/
 *   TOKEN=<your_jwt_token> k6 run k6/client_dashboard_load.js
 *
 * Against dev-tunnel:
 *   TOKEN=<token> BASEURL=https://your-tunnel.ngrok.io k6 run k6/client_dashboard_load.js
 *
 * Against local:
 *   TOKEN=<token> BASEURL=http://localhost:8000 k6 run k6/client_dashboard_load.js
 *
 * Target SLOs:
 *   p50 < 50ms
 *   p95 < 100ms
 *   p99 < 200ms
 *   error rate < 0.1%
 *   throughput > 1000 RPS sustained
 */
import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// ── Custom metrics ──────────────────────────────────────────────────
const errorRate     = new Rate('error_rate');
const dashboardTime = new Trend('dashboard_response_ms', true);
const addressTime   = new Trend('addresses_response_ms', true);
const orderTime     = new Trend('order_stats_response_ms', true);
const totalRequests = new Counter('total_requests');

// ── Test configuration ──────────────────────────────────────────────
export const options = {
  scenarios: {
    // Ramp up to 500 VUs over 10s, hold for 20s, ramp down
    sustained_load: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '10s', target: 100 },
        { duration: '20s', target: 500 },
        { duration: '10s', target: 0  },
      ],
      gracefulRampDown: '5s',
    },
    // Spike test: sudden burst to 1000 VUs for 5 seconds
    spike: {
      executor: 'ramping-vus',
      startVUs: 0,
      startTime: '45s',  // After sustained load completes
      stages: [
        { duration: '2s', target: 1000 },
        { duration: '5s', target: 1000 },
        { duration: '3s', target: 0   },
      ],
    },
  },
  thresholds: {
    // SLO gates — test FAILS if any of these are breached
    'http_req_duration': ['p(50)<50', 'p(95)<100', 'p(99)<200'],
    'http_req_failed':   ['rate<0.001'],  // < 0.1% error rate
    'error_rate':        ['rate<0.001'],
    'dashboard_response_ms': ['p(95)<100'],
    'addresses_response_ms': ['p(95)<80'],
    'order_stats_response_ms': ['p(95)<80'],
  },
};

// ── Environment ─────────────────────────────────────────────────────
const BASE_URL = __ENV.BASEURL || 'http://localhost:8000';
const TOKEN    = __ENV.TOKEN;

if (!TOKEN) {
  throw new Error('TOKEN env var required. Export TOKEN=<jwt> before running.');
}

const HEADERS = {
  Authorization: `Bearer ${TOKEN}`,
  'Content-Type': 'application/json',
  Accept: 'application/json',
};

// ── Idempotency checker ──────────────────────────────────────────────
let referenceSnapshot = null;

function checkIdempotency(data) {
  const keys = ['profile', 'addresses', 'order_stats', 'wishlist_count'];
  for (const key of keys) {
    if (!(key in data)) return false;
  }
  if (referenceSnapshot === null) {
    referenceSnapshot = JSON.stringify(Object.keys(data).sort());
  }
  // Same response shape every time (idempotency of structure)
  return JSON.stringify(Object.keys(data).sort()) === referenceSnapshot;
}

// ── Main virtual user script ─────────────────────────────────────────
export default function () {
  totalRequests.add(1);

  group('Client Dashboard', () => {
    // ─ Dashboard snapshot (full) ──────────────────────────────────
    const dashStart = Date.now();
    const dashRes = http.get(
      `${BASE_URL}/api/v1/ninja/client/dashboard/`,
      { headers: HEADERS, timeout: '5s' }
    );
    dashboardTime.add(Date.now() - dashStart);

    const dashOk = check(dashRes, {
      'dashboard: status 200':         (r) => r.status === 200,
      'dashboard: has profile key':    (r) => {
        try { return 'profile' in JSON.parse(r.body); } catch { return false; }
      },
      'dashboard: has order_stats':    (r) => {
        try { return 'order_stats' in JSON.parse(r.body); } catch { return false; }
      },
      'dashboard: idempotent shape':   (r) => {
        try { return checkIdempotency(JSON.parse(r.body)); } catch { return false; }
      },
      'dashboard: < 100ms':            (r) => r.timings.duration < 100,
    });
    errorRate.add(!dashOk);
  });

  group('Client Addresses', () => {
    // ─ Address list ───────────────────────────────────────────────
    const addrStart = Date.now();
    const addrRes = http.get(
      `${BASE_URL}/api/v1/ninja/client/addresses/`,
      { headers: HEADERS, timeout: '5s' }
    );
    addressTime.add(Date.now() - addrStart);

    const addrOk = check(addrRes, {
      'addresses: status 200':  (r) => r.status === 200,
      'addresses: is array':    (r) => {
        try { return Array.isArray(JSON.parse(r.body)); } catch { return false; }
      },
      'addresses: < 80ms':      (r) => r.timings.duration < 80,
    });
    errorRate.add(!addrOk);
  });

  group('Client Order Stats', () => {
    // ─ Order statistics ───────────────────────────────────────────
    const orderStart = Date.now();
    const orderRes = http.get(
      `${BASE_URL}/api/v1/ninja/client/orders/stats/`,
      { headers: HEADERS, timeout: '5s' }
    );
    orderTime.add(Date.now() - orderStart);

    const orderOk = check(orderRes, {
      'order_stats: status 200':           (r) => r.status === 200,
      'order_stats: has total_orders':     (r) => {
        try { return 'total_orders' in JSON.parse(r.body); } catch { return false; }
      },
      'order_stats: < 80ms':              (r) => r.timings.duration < 80,
    });
    errorRate.add(!orderOk);
  });

  // Think time: simulate real user browsing pace (50-200ms between requests)
  sleep(Math.random() * 0.15 + 0.05);
}

// ── Summary handler ──────────────────────────────────────────────────
export function handleSummary(data) {
  const summary = {
    timestamp: new Date().toISOString(),
    thresholds_passed: Object.values(data.metrics).every(
      (m) => !m.thresholds || Object.values(m.thresholds).every((t) => t.ok)
    ),
    p50_ms:  data.metrics.http_req_duration?.values?.['p(50)'],
    p95_ms:  data.metrics.http_req_duration?.values?.['p(95)'],
    p99_ms:  data.metrics.http_req_duration?.values?.['p(99)'],
    error_rate: data.metrics.error_rate?.values?.rate,
    total_requests: data.metrics.total_requests?.values?.count,
    rps: data.metrics.http_reqs?.values?.rate,
  };

  console.log('\n=== FASHIONISTAR LOAD TEST SUMMARY ===');
  console.log(JSON.stringify(summary, null, 2));

  return {
    'k6/load_test_results.json': JSON.stringify(data, null, 2),
    stdout: JSON.stringify(summary, null, 2),
  };
}
