import http from 'k6/http';
import { check, sleep } from 'k6';
import { SharedArray } from 'k6/data';

/**
 * FASHIONISTAR — Industrial-Grade K6 Stress Test
 * Targets: 10k+ RPS / 100k Concurrent Users
 * Focus: Authentication, Profile Hydration, and API Gateway Performance
 */

export const options = {
  scenarios: {
    stress_test: {
      executor: 'ramping-arrival-rate',
      startRate: 100,
      timeUnit: '1s',
      preAllocatedVUs: 1000,
      maxVUs: 5000,
      stages: [
        { duration: '2m', target: 5000 },  // Ramp up to 5k RPS
        { duration: '5m', target: 5000 },  // Stay at 5k RPS
        { duration: '2m', target: 10000 }, // Ramp up to 10k RPS
        { duration: '5m', target: 10000 }, // Stay at 10k RPS
        { duration: '2m', target: 0 },     // Ramp down
      ],
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<100', 'p(99)<250'], // 95% of requests must be < 100ms
    http_req_failed: ['rate<0.001'],               // Error rate < 0.1%
  },
};

const BASE_URL = __ENV.API_URL || 'http://localhost:8000/api/v1';

// Simulated users data (normally loaded from a JSON file)
const users = new SharedArray('users', function () {
  return [
    { email: 'stress_test_1@fashionistar.ai', password: 'Password123!' },
    { email: 'stress_test_2@fashionistar.ai', password: 'Password123!' },
  ];
});

export default function () {
  const user = users[Math.floor(Math.random() * users.length)];

  // 1. Login Attempt
  const loginRes = http.post(`${BASE_URL}/auth/login/`, JSON.stringify({
    email_or_phone: user.email,
    password: user.password,
  }), {
    headers: { 'Content-Type': 'application/json' },
  });

  check(loginRes, {
    'login status is 200': (r) => r.status === 200,
    'has access token': (r) => r.json().access !== undefined,
  });

  if (loginRes.status === 200) {
    const accessToken = loginRes.json().access;

    // 2. Profile Rehydration (SSR simulation)
    const meRes = http.get(`${BASE_URL}/auth/me/`, {
      headers: { 'Authorization': `Bearer ${accessToken}` },
    });

    check(meRes, {
      'me status is 200': (r) => r.status === 200,
      'user_id matches': (r) => r.json().email === user.email,
    });

    // 3. Category Reference Data (Global fetch simulation)
    const categoriesRes = http.get(`${BASE_URL}/home/categories/`);
    check(categoriesRes, {
      'categories status is 200': (r) => r.status === 200,
    });
  }

  sleep(Math.random() * 0.5 + 0.1); // Small jitter
}
