from django.db import models
from django.conf import settings
from django.utils import timezone

User = settings.AUTH_USER_MODEL

# Re-export LoginAttempt so Django's app registry picks it up.
# The class lives in its own file because it has different lifecycle /
# retention concerns than the rest of this module.
from .login_attempt_models import LoginAttempt, LoginAttemptFailureReason  # noqa: F401,E402


class FraudAlert(models.Model):
    """Flag suspicious orders or user behaviour automatically."""
    SEVERITY_CHOICES = (
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    )
    TYPE_CHOICES = (
        ('high_value_new_account', 'High Value Order from New Account'),
        ('multiple_failed_payments', 'Multiple Failed Payments'),
        ('unusual_location', 'Unusual Login Location'),
        ('rapid_orders', 'Rapid Successive Orders'),
        ('multiple_accounts', 'Suspected Multiple Accounts'),
        ('chargeback_history', 'Chargeback History'),
        ('banned_keyword', 'Banned Keyword in Product'),
    )

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='fraud_alerts', null=True, blank=True
    )
    order = models.ForeignKey(
        'orders.Order', on_delete=models.SET_NULL, null=True, blank=True, related_name='fraud_alerts'
    )
    type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='medium')
    description = models.TextField()
    is_resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_fraud_alerts'
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.type} — {self.severity}"


class IPBan(models.Model):
    """Block specific IP addresses."""
    ip_address = models.GenericIPAddressField(unique=True)
    reason = models.TextField()
    banned_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='ip_bans'
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_active(self):
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        return True

    def __str__(self):
        return f"IP Ban: {self.ip_address}"


class BannedKeyword(models.Model):
    """Keywords that auto-flag products for review."""
    keyword = models.CharField(max_length=100, unique=True)
    severity = models.CharField(max_length=10, choices=(
        ('warn', 'Warn'), ('block', 'Block Immediately')
    ), default='warn')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.keyword


class ContentModerationFlag(models.Model):
    """Auto-flagged content for admin review."""
    CONTENT_TYPE_CHOICES = (
        ('product', 'Product'),
        ('review', 'Review'),
        ('message', 'Message'),
        ('profile', 'Profile'),
    )
    content_type = models.CharField(max_length=15, choices=CONTENT_TYPE_CHOICES)
    content_id = models.PositiveIntegerField()
    reason = models.CharField(max_length=200)
    keyword_matched = models.CharField(max_length=100, blank=True)
    is_resolved = models.BooleanField(default=False)
    action_taken = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


# ── Fraud Detection Logic ─────────────────────────────────────

def check_order_fraud(order):
    """
    Run automated fraud checks on a new order.
    Call this after order creation.
    """
    alerts = []
    user = order.buyer

    # High value order from new account (< 7 days old)
    from datetime import timedelta
    if float(order.total) > 50000:  # 50,000 AOA
        account_age = (timezone.now() - user.date_joined).days
        if account_age < 7:
            alerts.append(FraudAlert.objects.create(
                user=user, order=order,
                type='high_value_new_account',
                severity='high',
                description=f'Order total {order.total} AOA from account created {account_age} days ago.',
            ))

    # Rapid successive orders (3+ orders in 1 hour)
    from apps.orders.models import Order
    recent_orders = Order.objects.filter(
        buyer=user,
        created_at__gte=timezone.now() - timedelta(hours=1)
    ).count()
    if recent_orders >= 3:
        alerts.append(FraudAlert.objects.create(
            user=user, order=order,
            type='rapid_orders',
            severity='medium',
            description=f'{recent_orders} orders placed in the last hour.',
        ))

    return alerts


def check_product_content(product):
    """Scan product title/description for banned keywords."""
    banned = BannedKeyword.objects.all()
    text = f"{product.title} {product.description}".lower()
    for kw in banned:
        if kw.keyword.lower() in text:
            ContentModerationFlag.objects.create(
                content_type='product',
                content_id=product.pk,
                reason=f'Banned keyword detected',
                keyword_matched=kw.keyword,
            )
            if kw.severity == 'block':
                product.is_active = False
                product.save(update_fields=['is_active'])
            break


# ─── AliExpress Security Engineering Workflow §13.1 / §16.1 ─────────

import hashlib as _hl
from django.conf import settings as _set
from django.db import models as _m
from django.utils import timezone as _tz


class TrustedDevice(_m.Model):
    """Per-user known-device registry.

    A device fingerprint is a stable hash of:
        sha256(user_agent + accept_language + ip_subnet_/24 + screen_size?)
    First time we see a fingerprint for a user, we mark the row
    ``first_seen_at=now()`` and ``alert_sent=True`` and fire a
    "new device login" notification. Subsequent logins update
    ``last_seen_at``.

    This is the foundation for §13.2 continuous risk monitoring:
    a sudden burst of activity from an unknown fingerprint =
    candidate account takeover.
    """
    # NOTE: ``related_name='known_devices'`` (not ``trusted_devices``)
    # to avoid clashing with django-two-factor-auth's TrustedDevice
    # model which already owns that reverse accessor on User.
    user = _m.ForeignKey(_set.AUTH_USER_MODEL, on_delete=_m.CASCADE,
                         related_name='known_devices', db_index=True)
    fingerprint = _m.CharField(max_length=64, db_index=True)  # sha256 hex
    user_agent = _m.CharField(max_length=255, blank=True)
    ip = _m.GenericIPAddressField(null=True, blank=True)
    country = _m.CharField(max_length=2, blank=True)
    first_seen_at = _m.DateTimeField(auto_now_add=True)
    last_seen_at = _m.DateTimeField(auto_now=True)
    alert_sent = _m.BooleanField(default=False)
    revoked_at = _m.DateTimeField(null=True, blank=True)
    label = _m.CharField(max_length=80, blank=True)  # user-editable

    class Meta:
        unique_together = ('user', 'fingerprint')
        ordering = ['-last_seen_at']
        indexes = [_m.Index(fields=['user', 'last_seen_at'])]

    @staticmethod
    def fingerprint_from_request(request) -> str:
        """Build a stable per-device fingerprint from request headers."""
        ua = (request.META.get('HTTP_USER_AGENT') or '')[:255]
        lang = (request.META.get('HTTP_ACCEPT_LANGUAGE') or '')[:40]
        ip = request.META.get('REMOTE_ADDR') or ''
        # Use /24 subnet so a roaming mobile keeps the same fingerprint.
        subnet = '.'.join(ip.split('.')[:3]) if '.' in ip else ip
        raw = f'{ua}|{lang}|{subnet}'
        return _hl.sha256(raw.encode()).hexdigest()

    def __str__(self):
        return f'{self.user_id} · {self.fingerprint[:8]}…'


class SecurityAuditLog(_m.Model):
    """Spec §16.1 — append-only audit trail for sensitive actions.

    Distinct from analytics.UserEvent (analytics is high-volume,
    low-importance click-stream). This table records ONLY actions a
    SecOps reviewer cares about: password changes, 2FA changes,
    permission grants, suspicious-login triggers, admin overrides.
    """
    ACTION_CHOICES = (
        ('password_changed',     'Password changed'),
        ('email_changed',        'Email changed'),
        ('phone_changed',        'Phone changed'),
        ('2fa_enabled',          '2FA enabled'),
        ('2fa_disabled',         '2FA disabled'),
        ('login_new_device',     'Login from new device'),
        ('login_new_country',    'Login from new country'),
        ('account_suspended',    'Account suspended'),
        ('account_reactivated',  'Account reactivated'),
        ('permission_granted',   'Permission granted'),
        ('permission_revoked',   'Permission revoked'),
        ('admin_override',       'Admin override'),
        ('session_revoked',      'Session revoked'),
        ('jwt_rotation',         'JWT version bumped'),
        ('csp_violation',        'CSP violation reported'),
    )
    user = _m.ForeignKey(_set.AUTH_USER_MODEL, on_delete=_m.SET_NULL, null=True, blank=True,
                         related_name='security_audit_logs', db_index=True)
    actor = _m.ForeignKey(_set.AUTH_USER_MODEL, on_delete=_m.SET_NULL, null=True, blank=True,
                          related_name='+', help_text='Admin who performed the action, if any')
    action = _m.CharField(max_length=30, choices=ACTION_CHOICES, db_index=True)
    ip = _m.GenericIPAddressField(null=True, blank=True)
    user_agent = _m.CharField(max_length=255, blank=True)
    details = _m.JSONField(default=dict, blank=True)
    created_at = _m.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            _m.Index(fields=['action', '-created_at']),
            _m.Index(fields=['user', '-created_at']),
        ]

    def __str__(self):
        return f'{self.action} · user={self.user_id} · {self.created_at:%Y-%m-%d %H:%M}'


def audit(action: str, *, user=None, actor=None, request=None, details=None):
    """Convenience writer for security_audit_log.

    Always wrap in try/except: an audit-log write failure must not
    crash the user request (we log + continue).
    """
    try:
        ip = None
        ua = ''
        if request is not None:
            ip = request.META.get('REMOTE_ADDR') or None
            ua = (request.META.get('HTTP_USER_AGENT') or '')[:255]
        SecurityAuditLog.objects.create(
            user=user, actor=actor, action=action,
            ip=ip, user_agent=ua, details=details or {},
        )
    except Exception:
        # Never let audit failure break the user request.
        pass


def record_device_login(user, request) -> tuple['TrustedDevice', bool]:
    """Register / refresh a TrustedDevice. Returns (row, is_new).

    Callers (login view, refresh-token view) should call this on
    every successful auth event. ``is_new=True`` is the trigger to
    send the user a "new device sign-in" email.
    """
    fp = TrustedDevice.fingerprint_from_request(request)
    ua = (request.META.get('HTTP_USER_AGENT') or '')[:255]
    ip = request.META.get('REMOTE_ADDR') or None
    row, created = TrustedDevice.objects.get_or_create(
        user=user, fingerprint=fp,
        defaults={'user_agent': ua, 'ip': ip, 'first_seen_at': _tz.now()},
    )
    if not created:
        row.last_seen_at = _tz.now()
        if ip and row.ip != ip:
            row.ip = ip
        row.save(update_fields=['last_seen_at', 'ip'])
    else:
        row.alert_sent = True
        row.save(update_fields=['alert_sent'])
        audit('login_new_device', user=user, request=request,
              details={'fingerprint': fp[:16], 'user_agent': ua[:80]})
        # Best-effort email — never crash the auth flow if SMTP is down.
        try:
            from django.core.mail import send_mail
            from django.conf import settings as dj_settings
            send_mail(
                subject='Novo login na sua conta MICHA',
                message=(
                    f'Detectámos um login a partir de um novo dispositivo:\n\n'
                    f'• Dispositivo: {ua[:120] or "desconhecido"}\n'
                    f'• IP: {ip or "desconhecido"}\n'
                    f'• Quando: {_tz.now():%Y-%m-%d %H:%M %Z}\n\n'
                    f'Se não foi você, mude já a sua palavra-passe.\n'
                ),
                from_email=getattr(dj_settings, 'DEFAULT_FROM_EMAIL', None),
                recipient_list=[user.email] if user.email else [],
                fail_silently=True,
            )
        except Exception:
            pass
    return row, created
