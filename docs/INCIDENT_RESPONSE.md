# MICHA — Security Incident Response Plan

## Overview
This document defines the procedure for detecting, containing, and recovering from
security incidents. Angola's Lei 22/11 requires notifying affected individuals
within 72 hours of a confirmed personal data breach.

---

## Severity Classification

| Level | Description | Examples | Response Time |
|-------|-------------|---------|---------------|
| P0 — Critical | Active breach, data exfiltration | DB compromised, credentials leaked | Immediate |
| P1 — High | Security control bypassed | Admin account hijacked, payment fraud | 1 hour |
| P2 — Medium | Attempted attack detected | SQLi probing, brute force | 4 hours |
| P3 — Low | Suspicious activity | Unusual login, scraping | 24 hours |

---

## Phase 1 — Detection & Triage (0–30 minutes)

**Who is on call?** Check the on-call schedule. Escalate to CTO if P0/P1.

**Detection sources:**
- Sentry alerts (application errors)
- Security logger (`micha.security` stream)
- UptimeRobot /health/ failures
- User reports via support
- Cloudflare WAF alerts

**Triage steps:**
1. Confirm it's a real incident (not a false positive)
2. Classify severity (P0–P3)
3. Page the on-call engineer and CTO (P0/P1)
4. Create an incident Slack channel: `#incident-YYYY-MM-DD`
5. Document everything in real time in the channel

---

## Phase 2 — Containment (30 min – 2 hours)

### If database is compromised:
```bash
# 1. Rotate DB password immediately
# In RDS: modify instance, change master password

# 2. Rotate SECRET_KEY (invalidates all JWT tokens — all users logged out)
# Update .env SECRET_KEY, redeploy

# 3. Rotate FIELD_ENCRYPTION_KEY (re-encrypt all encrypted fields)
python manage.py shell
>>> from apps.payments.models import SellerBankAccount
>>> # Re-encrypt all records with new key

# 4. Take DB offline if breach is active
docker-compose stop db

# 5. Preserve forensic evidence BEFORE any cleanup
pg_dump micha > /tmp/forensic_$(date +%Y%m%d_%H%M%S).dump
```

### If admin credentials are compromised:
```bash
# 1. Force-revoke all admin JWT tokens
python manage.py shell
>>> from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
>>> from django.contrib.auth import get_user_model
>>> User = get_user_model()
>>> admin = User.objects.get(email='admin@micha.app')
>>> for token in OutstandingToken.objects.filter(user=admin):
...     BlacklistedToken.objects.get_or_create(token=token)

# 2. Change admin password
>>> admin.set_password('new-strong-password-here')
>>> admin.save()

# 3. Add admin IP to allowlist immediately
# In settings.py: ADMIN_ALLOWED_IPS = ['YOUR_IP']
```

### If payment webhook is under attack:
```bash
# 1. Block webhook endpoint in nginx
# Add to nginx config:
location /api/payments/webhook/ {
    return 503;
}
nginx -s reload

# 2. Audit fake payments
python manage.py shell
>>> from apps.payments.models import WalletTransaction
>>> suspicious = WalletTransaction.objects.filter(
...     description__contains='Order',
...     created_at__gte='today'
... )
```

### If credential stuffing detected:
```bash
# 1. Check login failure rate
grep "failed_login" /var/log/micha/security.log | wc -l

# 2. Block attacking IPs in Cloudflare WAF

# 3. Force 2FA for all sellers temporarily
python manage.py shell
>>> from django.contrib.auth import get_user_model
>>> User = get_user_model()
>>> User.objects.filter(is_seller=True).update(two_fa_enabled=True)
```

---

## Phase 3 — Eradication

1. Identify root cause (how did attacker get in?)
2. Patch the vulnerability
3. Scan for backdoors or persistent access
4. Verify all compromised credentials are rotated
5. Restore from last known good backup if data is corrupted

---

## Phase 4 — Breach Notification (within 72 hours)

### If personal data was accessed or exfiltrated:

**Angola Lei 22/11 requires:**
- Notify ANPD (Agência Nacional de Protecção de Dados) within 72 hours
- Notify affected individuals without undue delay
- Document: what happened, what data, how many people, what action taken

**ANPD Contact:**
- Website: www.anpd.gv.ao
- Email: geral@anpd.gv.ao

**User notification template:**
```
Subject: Important security notice about your MICHA account

Dear [Name],

We are writing to inform you of a security incident that may have affected
your MICHA account.

What happened: [Brief description]
What data was involved: [email / phone / order history]
What we have done: [Actions taken]
What you should do: [Change password, enable 2FA, monitor account]

We sincerely apologise for this incident. Your security is our priority.

If you have questions, contact us at security@micha.app

— The MICHA Team
```

---

## Phase 5 — Post-Incident Review (within 1 week)

1. Write a full post-mortem document
2. Timeline of events
3. Root cause analysis
4. What went well
5. What to improve
6. Action items with owners and deadlines
7. Share with team (blameless culture)

---

## Data Classification Reference

| Tier | Data | Encryption | Retention |
|------|------|-----------|-----------|
| Public | Product listings, store names | None | Indefinite |
| Internal | Analytics, funnel events | In transit | 1 year |
| Confidential | Orders, reviews, addresses | In transit | 7 years |
| Restricted | Bank accounts, national ID, OTPs | At rest + in transit | Minimum necessary |

---

## Emergency Contacts

| Role | Contact | When to call |
|------|---------|-------------|
| Lead Engineer | TBD | P0, P1 |
| CTO | TBD | P0 |
| Legal Counsel | TBD | Any data breach |
| ANPD | geral@anpd.gv.ao | Data breach involving PII |
| Cloudflare Support | dash.cloudflare.com | DDoS, WAF issues |
| AWS Support | aws.amazon.com/support | Infrastructure issues |
