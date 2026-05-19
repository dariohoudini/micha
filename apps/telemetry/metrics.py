"""
Prometheus metrics catalogue for MICHA.

Convention: micha_<domain>_<unit>_<verb>

Counters increment forever (Prometheus computes rates from them).
Gauges show "current value" — refreshed by scheduled jobs.
Histograms record latency / value distributions.

All metric names are stable contracts — once a dashboard is wired to a
metric, renaming breaks it. Add new ones; don't rename old ones.
"""
from prometheus_client import Counter, Gauge, Histogram


# ── Orders / commerce ───────────────────────────────────────────────
orders_created = Counter(
    'micha_orders_created_total',
    'Orders created at checkout (any payment status).',
    ['payment_method'],
)
orders_status_transitions = Counter(
    'micha_orders_status_transitions_total',
    'Order.status transitions.',
    ['from_status', 'to_status'],
)
checkout_blocked_by_risk = Counter(
    'micha_checkout_blocked_by_risk_total',
    'Checkouts blocked by the fraud engine.',
)
checkout_stock_contention = Counter(
    'micha_checkout_stock_contention_total',
    'Checkouts that failed because stock changed between cart-view and '
    'the locked decrement. High counts = flash-sale traffic; sudden '
    'spikes = a popular product just hit zero.',
    ['reason'],   # 'product_oversold' | 'variant_oversold' | 'product_vanished'
)
stock_restored_total = Counter(
    'micha_stock_restored_total',
    'Inventory units put back via the restore-stock primitive '
    '(payment_failed, abandoned_checkout, manual_cancel).',
    ['source'],   # 'payment_failed' | 'abandoned_checkout' | 'manual_cancel'
)

# ── Payments ────────────────────────────────────────────────────────
payments_confirmed = Counter(
    'micha_payments_confirmed_total',
    'Successful payment confirmations.',
    ['method'],
)
payments_failed = Counter(
    'micha_payments_failed_total',
    'Failed payments.',
    ['method', 'reason'],
)
payment_confirm_latency = Histogram(
    'micha_payment_confirm_latency_seconds',
    'Time from payment.confirm() entry to commit.',
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)

# ── Buyer Protection ───────────────────────────────────────────────
protection_lapsed = Counter(
    'micha_protection_lapsed_total',
    'Orders auto-actioned due to protection deadline lapse.',
    ['from_state'],
)

# ── Refunds / Returns ───────────────────────────────────────────────
refunds_issued = Counter(
    'micha_refunds_issued_total',
    'Refunds posted (any source).',
    ['source', 'destination'],  # source: protection|return|admin; dest: store_credit|gateway
)
refunds_amount_kz = Counter(
    'micha_refunds_amount_kz_total',
    'Sum of Kz refunded.',
    ['source', 'destination'],
)

# ── Risk engine ─────────────────────────────────────────────────────
risk_assessments = Counter(
    'micha_risk_assessments_total',
    'Risk assessments computed.',
    ['scope', 'action'],  # scope: order|signup; action: allow|flag|hold|block
)

# ── Ledger ──────────────────────────────────────────────────────────
ledger_journals_posted = Counter(
    'micha_ledger_journals_posted_total',
    'Ledger journals successfully posted.',
    ['ref_type'],
)
ledger_imbalance_cents = Gauge(
    'micha_ledger_imbalance_cents',
    'Σ credits − Σ debits per currency (must be 0; otherwise alert).',
    ['currency'],
)
ledger_unbalanced_journals = Gauge(
    'micha_ledger_unbalanced_journals',
    'Count of journals where Σ debits ≠ Σ credits. Should always be 0; '
    'non-zero means a write path bypassed service.post().',
)
ledger_cached_counter_drift_count = Gauge(
    'micha_ledger_cached_counter_drift_count',
    'Count of users whose cached counters (store_credit, loyalty_points, '
    'seller wallet) drift from the ledger truth. Run hourly by the '
    'reconciliation beat task.',
)
ledger_cached_counter_drift_cents = Gauge(
    'micha_ledger_cached_counter_drift_cents',
    'Aggregate signed magnitude of cached-counter drift across all users. '
    'Positive = cached values exceed ledger (user sees more than they own); '
    'negative = ledger exceeds cached (user sees less than they own).',
)

# ── Inbound webhooks ────────────────────────────────────────────────
inbound_webhook_failure_rate_1h = Gauge(
    'micha_inbound_webhook_failure_rate_1h',
    'Fraction of inbound webhooks that failed verification or handler '
    'execution in the last hour. Alert at >0.05.',
)
inbound_webhook_failures_1h = Gauge(
    'micha_inbound_webhook_failures_1h',
    'Absolute count of failed inbound webhooks in the last hour.',
)
inbound_webhook_total_1h = Gauge(
    'micha_inbound_webhook_total_1h',
    'Absolute count of inbound webhooks received in the last hour.',
)

# ── Outbox ──────────────────────────────────────────────────────────
outbox_published = Counter(
    'micha_outbox_published_total',
    'Outbox events published (publish() calls that created a row).',
    ['topic'],
)
outbox_dispatched = Counter(
    'micha_outbox_dispatched_total',
    'Outbox events successfully dispatched (handler returned).',
    ['topic'],
)
outbox_dispatch_failed = Counter(
    'micha_outbox_dispatch_failed_total',
    'Outbox events whose handler raised.',
    ['topic'],
)
outbox_pending = Gauge(
    'micha_outbox_pending',
    'Current count of OutboxEvent in pending or retrying state.',
)
outbox_dead = Gauge(
    'micha_outbox_dead',
    'Current count of OutboxEvent in dead state (max attempts reached).',
)
outbox_dispatch_latency = Histogram(
    'micha_outbox_dispatch_latency_seconds',
    'Time inside dispatch_one() — handler execution + DB write.',
    buckets=(0.005, 0.01, 0.05, 0.1, 0.5, 1, 5, 30),
)
outbox_oldest_dead_age_seconds = Gauge(
    'micha_outbox_oldest_dead_age_seconds',
    'Age of the oldest DEAD event still sitting in the outbox table. '
    'Alert if this exceeds ~24h — somebody is not watching the DLQ.',
)
outbox_stale_retrying = Gauge(
    'micha_outbox_stale_retrying',
    'Count of OutboxEvent in retrying state that have not progressed '
    'in >24h. Indicates a handler stuck in a silent-failure loop or '
    'a downstream that keeps hard-failing past max-backoff.',
)

# ── Search ──────────────────────────────────────────────────────────
search_queries = Counter(
    'micha_search_queries_total',
    'Search query executions.',
    ['has_results'],  # 'yes' | 'no'
)
search_latency = Histogram(
    'micha_search_latency_seconds',
    'Time to compute a search results page.',
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1),
)

# ── HTTP ────────────────────────────────────────────────────────────
http_requests = Counter(
    'micha_http_requests_total',
    'HTTP requests served.',
    ['method', 'route', 'status'],
)
http_request_latency = Histogram(
    'micha_http_request_latency_seconds',
    'Wall time per HTTP request.',
    ['route'],
    buckets=(0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)
http_db_queries = Histogram(
    'micha_http_db_queries',
    'DB queries executed per HTTP request — N+1 detector.',
    ['route'],
    buckets=(1, 5, 10, 25, 50, 100, 250, 500),
)

# ── Cache ───────────────────────────────────────────────────────────
cache_hits = Counter(
    'micha_cache_hits_total',
    'Cache lookups served from the cache (fresh or SWR-stale).',
)
cache_misses = Counter(
    'micha_cache_misses_total',
    'Cache lookups that required loading from source.',
)
cache_stampedes_avoided = Counter(
    'micha_cache_stampedes_avoided_total',
    'Concurrent requests that waited on a single-flight rebuild instead of '
    'all hitting the loader.',
)

# ── Feed ────────────────────────────────────────────────────────────
feed_served = Counter(
    'micha_feed_served_total',
    'Personalized feed builds served.',
    ['section'],
)
