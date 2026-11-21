import http from "k6/http";
import { check } from "k6";

const BASE = __ENV.BASE_URL || "http://finguard-backend:8000";
export const options = {
  vus: 10,
  duration: "20s",
  thresholds: { http_req_failed: ["rate<0.01"], http_req_duration: ["p(95)<750"] },
};

export function setup() {
  const login = http.post(`${BASE}/auth/login`, JSON.stringify({
    email: __ENV.ADMIN_EMAIL || "admin@finguard.com",
    password: __ENV.ADMIN_PASSWORD || "AdminPass123!",
  }), { headers: { "Content-Type": "application/json" } });
  const token = login.json("access_token");
  const h = { "Content-Type": "application/json", Authorization: `Bearer ${token}` };
  const me = http.get(`${BASE}/auth/me`, { headers: h }).json();
  const a1 = http.post(`${BASE}/accounts`, JSON.stringify({ user_id: me.id, name: "k6-src", currency: "USD" }), { headers: h }).json();
  const a2 = http.post(`${BASE}/accounts`, JSON.stringify({ user_id: me.id, name: "k6-dst", currency: "USD" }), { headers: h }).json();
  http.post(`${BASE}/deposits`, JSON.stringify({ account_id: a1.id, amount_cents: 1000000, description: "k6 seed" }), {
    headers: { ...h, "Idempotency-Key": `k6-seed-${Date.now()}` },
  });
  return { token, srcId: a1.id, dstId: a2.id };
}

export default function (data) {
  const key = `k6-${__VU}-${__ITER}-${Date.now()}`;
  const res = http.post(`${BASE}/transfers`, JSON.stringify({
    source_account_id: data.srcId,
    destination_account_id: data.dstId,
    amount_cents: 1,
    description: "k6 load transfer",
  }), { headers: { "Content-Type": "application/json", Authorization: `Bearer ${data.token}`, "Idempotency-Key": key } });
  check(res, { "transfer 201": (r) => r.status === 201 });
}

export function teardown(data) {
  const h = { Authorization: `Bearer ${data.token}` };
  const b1 = http.get(`${BASE}/accounts/${data.srcId}/balance`, { headers: h }).json("balance_cents");
  const b2 = http.get(`${BASE}/accounts/${data.dstId}/balance`, { headers: h }).json("balance_cents");
  console.log("PAIR_SUM:", b1 + b2);
  check(null, { "zero pair drift": () => b1 + b2 === 1000000 });
}
