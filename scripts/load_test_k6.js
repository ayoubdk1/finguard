import http from "k6/http";
import { check } from "k6";
export const options = { vus: 10, duration: "30s" };
export default function () { check(http.get(`${__ENV.BASE_URL || "http://127.0.0.1:8001"}/health/ready`), { "200": (r) => r.status === 200 }); }
