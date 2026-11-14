from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

HTTP_REQUESTS_TOTAL = Counter(
    "finguard_http_requests_total",
    "Total HTTP requests handled",
    ["method", "path", "status"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "finguard_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

FRAUD_RISK_SCORE = Histogram(
    "finguard_fraud_risk_score",
    "Distribution of transaction fraud risk scores",
    buckets=(0.0, 10.0, 25.0, 50.0, 75.0, 90.0, 100.0),
)

TRANSFERS_TOTAL = Counter(
    "finguard_transfers_total",
    "Total transfers processed by currency and status",
    ["currency", "status"],
)

RATE_LIMIT_HITS_TOTAL = Counter(
    "finguard_rate_limit_hits_total",
    "Total rate limit 429 rejections",
    ["limiter"],
)


def render_prometheus_metrics() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
