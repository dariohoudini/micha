# MICHA — Disaster Recovery Runbook

Every senior engineer expects this document to exist before going to production.
Covers: database failure, Redis failure, Celery failure, deploy rollback.

---

## 1. Database is down

**Symptoms:** 503 from /health/ with `"database": "error"`, all API requests fail.

**Immediate steps:**
```bash
# 1. Check if PostgreSQL is running
docker-compose ps db
# or on server:
sudo systemctl status postgresql

# 2. Check PostgreSQL logs
docker-compose logs db --tail=50

# 3. Restart PostgreSQL
docker-compose restart db
# or:
sudo systemctl restart postgresql

# 4. Check disk space (common cause)
df -h

# 5. Check connections limit
psql -U micha_user -d micha -c "SELECT count(*) FROM pg_stat_activity;"
```

**If data is corrupted — restore from backup:**
```bash
# List available backups in S3
aws s3 ls s3://micha-backups/db/

# Restore
aws s3 cp s3://micha-backups/db/micha_2026-04-05.dump.gz .
gunzip micha_2026-04-05.dump.gz
pg_restore -U micha_user -d micha micha_2026-04-05.dump
```

---

## 2. Redis is down

**Symptoms:** /health/ shows `"cache": "error"`, WebSocket chat offline, Celery not processing.

**Immediate steps:**
```bash
# 1. Restart Redis
docker-compose restart redis

# 2. Flush if corrupted
redis-cli FLUSHALL

# 3. Check memory
redis-cli INFO memory
```

**Impact without Redis:**
- WebSocket chat: offline (REST chat still works)
- Celery tasks: queued locally until Redis comes back
- Cache: falls back to LocMemCache (per-process, slower)
- Sessions: users may need to log in again

---

## 3. Celery workers are down

**Symptoms:** /health/ shows `"celery_workers": "no workers"`, price alerts not firing, earnings not releasing.

**Immediate steps:**
```bash
# 1. Check worker status
celery -A config inspect active

# 2. Restart workers
docker-compose restart celery_worker

# 3. Check for stuck tasks
celery -A config inspect reserved

# 4. Purge dead tasks (careful — this loses queued tasks)
celery -A config purge
```

**Manually trigger critical tasks if needed:**
```bash
python manage.py shell
>>> from apps.payments.tasks import release_held_earnings
>>> release_held_earnings.delay()
>>> from apps.orders.tasks import auto_complete_old_orders
>>> auto_complete_old_orders.delay()
```

---

## 4. Celery Beat is down

**Symptoms:** No scheduled tasks running (price alerts, digests etc).

```bash
# Restart Beat
docker-compose restart celery_beat

# Check Beat is running
docker-compose logs celery_beat --tail=20
```

---

## 5. Deploy rollback

**Symptoms:** After deploy, error rate spikes, /health/ fails.

```bash
# 1. Identify last good image tag
docker images | grep micha-api

# 2. Roll back to previous image
docker-compose stop api
docker tag micha-api:previous micha-api:latest
docker-compose up -d api

# 3. Roll back migration if schema changed
python manage.py migrate apps.orders 0015  # previous migration number
python manage.py migrate apps.users 0012
```

**Preventive: always test migrations on staging first:**
```bash
# Check if migrations are up to date before deploy
python manage.py migrate --check
```

---

## 6. Bad migration in production

**Symptoms:** Deploy fails with `django.db.utils.OperationalError`.

```bash
# 1. Find out which migration caused the issue
python manage.py showmigrations | grep '\[ \]'

# 2. Fake back to before the bad migration
python manage.py migrate apps.payments 0008 --fake

# 3. Roll back the code
git checkout HEAD~1

# 4. Redeploy
docker-compose up -d api
```

---

## 7. Disk full

**Symptoms:** 500 errors, logs say "No space left on device".

```bash
# Check disk usage
df -h
du -sh /var/lib/docker/*

# Clean Docker
docker system prune -af

# Clean old logs
truncate -s 0 /var/log/micha/*.log

# Clean old media (careful)
find /app/media/products/videos -mtime +90 -delete
```

---

## 8. Security incident — suspected breach

**Immediate steps (first 30 minutes):**

1. Rotate `SECRET_KEY` immediately → all JWT tokens invalidated, all users logged out
2. Rotate `FIELD_ENCRYPTION_KEY` → re-encrypt sensitive fields
3. Rotate DB password
4. Rotate Redis password
5. Check access logs for suspicious patterns: `grep "403\|401\|500" /var/log/nginx/access.log | awk '{print $1}' | sort | uniq -c | sort -rn | head -20`
6. Block suspicious IPs
7. Notify users if PII was accessed

---

## 9. Payment webhook attack

**Symptoms:** Seller wallets credited with no real payments, fake orders marked paid.

```bash
# 1. Immediately disable webhook endpoint in nginx
# Add to nginx config:
location /api/payments/webhook/ { return 403; }

# 2. Audit webhook logs
grep "Verified webhook" /var/log/micha/app.log | tail -100
grep "signature FAILED" /var/log/micha/app.log | tail -100

# 3. Identify and reverse fraudulent wallet credits
python manage.py shell
>>> from apps.payments.models import WalletTransaction
>>> suspicious = WalletTransaction.objects.filter(description__contains='Order', created_at__gte='2026-04-05')
>>> suspicious.count()

# 4. Rotate Flutterwave/Stripe webhook secrets
# In Flutterwave dashboard: Security → Webhook → Regenerate hash
# Update FLUTTERWAVE_SECRET_HASH in .env and redeploy
```

---

## Daily backup verification

Run this every morning to confirm backups are working:
```bash
# Check latest backup exists and is recent
aws s3 ls s3://micha-backups/db/ | tail -5

# Verify backup integrity
pg_restore --list s3://micha-backups/db/latest.dump | head -20
```

---

## On-call escalation

| Severity | Response time | Who to call |
|----------|---------------|-------------|
| P0 — site down | 15 min | CTO + Lead engineer |
| P1 — payments broken | 30 min | Lead engineer |
| P2 — feature broken | 2 hours | On-call engineer |
| P3 — minor bug | Next business day | Any engineer |
