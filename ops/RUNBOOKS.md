# MICHA Operational Runbooks

Each entry below is a specific incident or maintenance scenario with
concrete commands. Severity P0 = user-facing outage, P1 = degraded,
P2 = internal-only impact, P3 = bug to triage.

Practice quarterly via chaos drills (kill a pod, see if the runbook
works). Updates land via PR — never edit live during an incident.

---

## P0-01 — All API requests returning 5xx

**Symptoms** healthcheck red, error rate spike, `5xx` topping logs.

1. Check `/readyz` from outside the cluster: `curl https://micha.ao/readyz`
   - Green → frontend or CDN problem; see P1-01.
   - Red → Django can't serve requests.
2. Inspect gunicorn logs: `kubectl logs -l app=micha-web --tail=200`
3. If all workers are in `CRITICAL` due to DB connection refused:
   - `psql -h <DB_HOST> -U <DB_USER> -c '\l'` — confirm DB reachable.
   - Check RDS / Postgres dashboard for CPU / connections at 100%.
4. If DB is fine: `kubectl rollout undo deploy/micha-web` to revert the
   latest release. Inspect git log to find the offending commit.

## P0-02 — Payments processor (AppyPay) returning errors

**Symptoms** orders stuck at `payment_status=pending`, no `paid`
webhooks landing in `PaymentEvent`.

1. Check AppyPay status page.
2. Tail webhook receiver: `kubectl logs -l app=micha-web | grep webhook`.
3. Verify HMAC secret is current — `WEBHOOK_HMAC_SECRETS['appypay']`.
4. If AppyPay is up but we're 401-ing their webhooks:
   - Rotate webhook secret with AppyPay support.
   - `kubectl set env deploy/micha-web WEBHOOK_HMAC_SECRETS_APPYPAY=...`
5. If AppyPay is down: switch checkout banner to "Card payments
   temporarily unavailable, Multicaixa Express only" via feature flag.

## P0-03 — Beat scheduler stopped

**Symptoms** no scheduled tasks running; `enforce-data-retention-nightly`
gap > 24h; nightly reports missing.

1. Confirm: `kubectl get pods -l app=micha-beat`.
2. Beat is a SINGLETON — only one replica allowed.
   `kubectl scale deploy/micha-beat --replicas=1` (NEVER 2+).
3. If pod is `CrashLoopBackOff`: `kubectl logs -p -l app=micha-beat`.
4. Common cause: Redis-locked singleton lock not released after a
   pod kill. Drop the lock manually:
   `kubectl exec -it <web-pod> -- python -c "import redis;
    r = redis.from_url('$REDIS_URL'); r.delete('celerybeat:lock')"`

## P0-04 — Database CPU 100%

**Symptoms** slow query alerts, p95 latency spike, connection pool
exhaustion.

1. `psql -c "SELECT pid, state, query_start, query FROM pg_stat_activity
   WHERE state='active' ORDER BY query_start LIMIT 20;"`
2. Identify the offending query — usually missing index or runaway loop.
3. KILL the worst offenders: `SELECT pg_cancel_backend(<pid>);`
4. If a deploy correlates: `kubectl rollout undo deploy/micha-web`.
5. Long-term: add the missing index (separate migration after incident).

## P0-05 — Outbox DLQ depth > 1000

**Symptoms** `payments.settlement.drift`, `webhooks.outbound.failed`,
or other DLQ topics accumulating. Buyers don't get notified, sellers
don't get paid on time.

1. Check DLQ size: `kubectl exec <web-pod> -- python manage.py
   shell -c "from apps.outbox.models import OutboxMessage;
   print(OutboxMessage.objects.filter(status='DEAD').count())"`
2. Inspect the top failures via admin: `/api/v1/admin/outbox/dlq/`.
3. If transient (e.g., FCM was down): bulk re-enqueue
   `POST /api/v1/admin/outbox/dlq/<id>/replay/`.
4. If structural (bad payload format): patch the consumer, deploy,
   then replay.

---

## P1-01 — Frontend bundle returning 502 / 404

**Symptoms** SPA blank screen; assets 404.

1. nginx logs: `kubectl logs -l app=micha-nginx --tail=100`.
2. Confirm `frontend/dist` deployed: `ls /srv/micha/frontend/dist/`.
3. If empty: re-run `npm run build` step in CI, redeploy.
4. If nginx isn't picking up new bundle: `kubectl rollout restart
   deploy/micha-nginx`.

## P1-02 — Cart abandonment task crashing

**Symptoms** ERROR log `Notification.objects.create() got unexpected
keyword argument` or similar. Buyers stop getting abandonment pushes.

1. The task was rewritten in commit `066a26c` to use `push_service`.
2. If errors return: check `Cart.last_abandonment_ping_at` field
   exists (migration 0004). Run `python manage.py migrate cart`.

## P1-03 — Image upload failing

**Symptoms** seller listing creation 500s on image upload.

1. Check disk free on the S3 / object-storage bucket.
2. If S3 returns 403: rotate IAM keys for `AWS_STORAGE_BUCKET_NAME`.
3. If pillow/avif unavailable: `pip install Pillow` in the image.

## P1-04 — Push notifications not delivering

**Symptoms** users report no order-shipped pushes.

1. Verify `FIREBASE_CREDENTIALS_PATH` env var is set and file exists.
2. Check token health: `SELECT COUNT(*) FROM notifications_device_token
   WHERE is_active=true AND deactivation_reason='';`
3. If most tokens are `fcm_unregistered`: app uninstalls — not an
   issue per se, but a leading indicator of churn.
4. If `FIREBASE_CREDENTIALS_PATH` is unset: `push_service` returns
   `{skipped: 1}` silently. Fix env var.

---

## P2-01 — Stripe / AppyPay settlement file failed to parse

**Symptoms** `SettlementReconRun.row_count = 0` for a day.

1. Inspect the file by hand. Common causes:
   - Encoding (Windows-1252 vs UTF-8).
   - Column-name changes (AppyPay has shifted `gateway_ref` ↔
     `gateway_reference` twice).
2. The parser is lenient — add the new column name as a synonym in
   `apps/payments/settlement.py:_normalise_row`.

## P2-02 — Cookie consent banner not appearing for new users

**Symptoms** banner missing, regulator complaint risk.

1. Check `/api/v1/account/data-request/consent/?consent_key=<x>`
   returns 200.
2. If returns the latest record with `has_consent=true`, the FE is
   short-circuiting. Inspect FE consent logic in
   `frontend/src/lib/consent.js` (when present).
3. Clear localStorage `micha-consent-key` to force banner.

## P2-03 — Data retention purger over-purging

**Symptoms** rows missing that shouldn't be (e.g., recent chat
messages disappeared).

1. Run in dry-run first to size impact:
   `python -c "from apps.data_rights.retention import enforce_retention;
   print(enforce_retention(dry_run=True))"`
2. Check `DATA_RETENTION_POLICY` env override didn't accidentally set
   a too-low number.

## P2-04 — Chargeback deadline approaching

**Symptoms** `Chargeback.deadline_at < now() + 24h` with
`status='received'`.

1. Query: `GET /api/v1/payments/chargebacks/?overdue=1`.
2. Assign to ops; submit evidence via `/respond/`.

## P2-05 — KYC tier cap blocking legitimate seller

**Symptoms** seller support ticket "I can't withdraw my own money".

1. Verify their tier: in shell, `from apps.payments.kyc_gating import
   resolve_tier; print(resolve_tier(user))`.
2. If they're Tier 1 but should be Tier 2: process their pending
   `SellerVerification` row, set status=approved.
3. If they're already Tier 3: bug — check
   `KYC_TIER3_MONTHLY_CAP_AOA` accidentally non-zero.

---

## P3-01 — pytest CI red

1. `make test` locally to reproduce.
2. If migrations issue: `make migrate` then re-run.
3. If timezone-warning: check the failing test isn't using naive
   `datetime` — should use `timezone.now()`.

## P3-02 — Cost telemetry showing endpoint at >$0.01/request

1. Look at `cost.request` logs filtered to that route.
2. `db_query_count` > 50 → N+1 candidate. Inspect query trace.
3. `response_bytes` > 1MB → consider pagination or sparse fields.

## P3-03 — Sentry showing JWT token in event extras

1. `apps/security/sentry_hook.py:before_send` is the PII scrub.
2. If a new token-bearing field landed, add its key pattern to
   `SENSITIVE_KEYS` in `frontend/src/lib/sentry.js` AND the backend
   redactor.

## P3-04 — Moderator queue backlog growing

1. `GET /api/v1/moderation/queue/?status=pending` shows depth.
2. If > 100 sustained: hire a moderator, or tune the auto-flag
   keyword list in `apps/moderation/service.py:_REVIEW_KEYWORDS`
   (likely false positives).

## P3-05 — AML alerts spiking

1. `GET /api/v1/payments/aml/alerts/?status=open` for depth.
2. If a single user is repeatedly flagged: review for true positive,
   else tune thresholds via `AML_*` settings.

---

## Maintenance — Restore drill (monthly)

Owner: SRE on-call.

1. `./scripts/restore_test.sh` in staging.
2. Verify ledger invariants pass.
3. Record run in the on-call channel + retention log.

## Maintenance — Secret rotation (quarterly)

Owner: Security lead.

1. AWS Secrets Manager → rotate `SECRET_KEY`, `FIELD_ENCRYPTION_KEY`,
   `JWT_SIGNING_KEY`.
2. Issue rolling restart of Django + worker pods.
3. Verify token-blacklist still functional (`/api/v1/auth/refresh/`).

## Maintenance — Dependency audit (quarterly)

Owner: Tech lead.

1. `pip-audit` + `npm audit` on prod requirements.
2. Patch CVEs flagged HIGH or CRITICAL within 30 days; LOW within 90.

## Maintenance — IVA filing (monthly)

Owner: Finance.

1. `GET /api/v1/tax/report/agt/?from=YYYY-MM-DD&to=YYYY-MM-DD&format=csv`
2. Submit via AGT portal by the 25th of the following month.

---

## On-call escalation

1. **L1** (24/7 rotation): triage, contain. 15min ack SLO.
2. **L2** (subject expert): payments / DBA / security as needed.
3. **L3** (founder + CTO): only for outages > 1h or money loss > 500k AOA.
