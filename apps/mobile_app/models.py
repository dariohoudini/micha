"""
Mobile App Engineering — server-side backbone for the mobile client.

Source: AliExpress_Mobile_App_Engineering.docx (24 chapters).
Chapters that live HERE (the rest are frontend patterns already shipped
in frontend/src/ — see the chapter map in services.py):

  CH4   Offline-first sync queue   → OfflineSyncReplay (replay audit + KPI source)
  CH11  Biometric authentication   → BiometricCredential / BiometricChallenge /
                                     BiometricPaymentToken
  CH13  Silent push                → SilentPushDispatch
  CH19  Crash reporting            → CrashGroup / CrashEvent
  CH20  Analytics event schema     → MobileAnalyticsEvent / MobileEventBatch
  CH21  A/B client-side eval       → MobileExperiment (config served to client)
  CH22  Deferred deep links        → DeferredDeepLink
  CH24  Mobile KPI dashboard       → AppRelease / ClientPerfMetric /
                                     MobileKpiSnapshot

NOT duplicated here (already exists elsewhere):
  apps.fraud_engine.DeviceFingerprint / DeviceUserLink  (CH12 server sync)
  apps.idempotency.IdempotencyKey                        (CH4/CH23 dedup)
  apps.flags.Flag / ExperimentExposure                   (server-side flags;
        MobileExperiment is the *client-side-eval* config the doc requires)
  apps.notifications.DeviceToken + push_service          (push transport)
  apps.analytics.UserEvent / FunnelEvent                 (web event sink;
        MobileAnalyticsEvent carries the mobile base schema: device_fp,
        ab_variants, network_type, app_version)
"""
from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


# ──────────────────────────────────────────────────────────────────────
# CH11 — Biometric authentication (FaceID / TouchID / fingerprint)
# ──────────────────────────────────────────────────────────────────────

class BiometricCredential(models.Model):
    """Public key generated in the device Secure Enclave / Keystore.

    The private key never leaves the device. Payment confirmation =
    device signs a server challenge; we verify with this public key.
    """
    ALGORITHM_CHOICES = [
        ('ec_p256', 'ECDSA P-256 / SHA-256'),
        ('rsa_2048', 'RSA-2048 PKCS#1 v1.5 / SHA-256'),
        ('dev_stub', 'Dev stub (SHA-256 echo — non-production)'),
    ]
    STATUS_CHOICES = [('active', 'Active'), ('revoked', 'Revoked')]

    user = models.ForeignKey(User, on_delete=models.CASCADE,
                             related_name='biometric_credentials')
    device_fingerprint = models.CharField(max_length=64, db_index=True)
    public_key_pem = models.TextField()
    algorithm = models.CharField(max_length=12, choices=ALGORITHM_CHOICES,
                                 default='ec_p256')
    platform = models.CharField(max_length=12, default='ios')  # ios/android/web
    biometry_type = models.CharField(max_length=24, blank=True)  # FaceID/TouchID/Fingerprint
    status = models.CharField(max_length=12, choices=STATUS_CHOICES,
                              default='active', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [('user', 'device_fingerprint')]

    def __str__(self):
        return f'biometric:{self.user_id}@{self.device_fingerprint[:8]}'


class BiometricChallenge(models.Model):
    """One-time server challenge the device must sign (anti-replay)."""
    PURPOSE_CHOICES = [
        ('payment', 'Payment confirmation'),
        ('login', 'Login unlock'),
        ('unlock', 'App unlock'),
    ]
    STATUS_CHOICES = [
        ('issued', 'Issued'), ('verified', 'Verified'),
        ('failed', 'Failed'), ('expired', 'Expired'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE,
                             related_name='biometric_challenges')
    credential = models.ForeignKey(BiometricCredential, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='challenges')
    purpose = models.CharField(max_length=12, choices=PURPOSE_CHOICES)
    order_ref = models.CharField(max_length=64, blank=True)
    challenge = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES,
                              default='issued', db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)  # 3 fails → fallback to PIN
    issued_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)


class BiometricPaymentToken(models.Model):
    """One-time token issued after a verified payment challenge."""
    user = models.ForeignKey(User, on_delete=models.CASCADE,
                             related_name='biometric_payment_tokens')
    challenge = models.OneToOneField(BiometricChallenge, on_delete=models.CASCADE,
                                     related_name='payment_token')
    token = models.CharField(max_length=64, unique=True)
    order_ref = models.CharField(max_length=64, blank=True)
    consumed = models.BooleanField(default=False)
    consumed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)


# ──────────────────────────────────────────────────────────────────────
# CH4 — Offline sync queue replay audit (server side)
# ──────────────────────────────────────────────────────────────────────

class OfflineSyncReplay(models.Model):
    """One row per offline-queued action replayed when connectivity
    returned. Source of the 'Offline Sync Success Rate' KPI (CH24).
    """
    ACTION_CHOICES = [
        ('add_to_cart', 'Add to cart'),
        ('wishlist_add', 'Wishlist add'),
        ('wishlist_remove', 'Wishlist remove'),
        ('review_submit', 'Review submit'),
        ('other', 'Other'),
    ]
    STATUS_CHOICES = [
        ('applied', 'Applied'),
        ('duplicate', 'Duplicate (idempotency hit)'),
        ('conflict', 'Conflict (server wins)'),
        ('failed', 'Failed (gave up after retries)'),
    ]

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                             blank=True, related_name='offline_sync_replays')
    device_fingerprint = models.CharField(max_length=64, blank=True, db_index=True)
    action_type = models.CharField(max_length=20, choices=ACTION_CHOICES)
    idempotency_key = models.CharField(max_length=64, unique=True)
    queued_at_client = models.DateTimeField(null=True, blank=True)
    retry_count = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, db_index=True)
    conflict_reason = models.CharField(max_length=120, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    replayed_at = models.DateTimeField(auto_now_add=True, db_index=True)


# ──────────────────────────────────────────────────────────────────────
# CH13 — Silent (data-only) push dispatch
# ──────────────────────────────────────────────────────────────────────

class SilentPushDispatch(models.Model):
    """Data-only push (no user-visible notification) that wakes the app
    in background: refresh cart, sync badge counts, pre-fetch deals.
    """
    PUSH_TYPE_CHOICES = [
        ('cart_update', 'Cart update'),
        ('price_drop', 'Price drop alert refresh'),
        ('badge_sync', 'Badge count sync'),
        ('content_prefetch', 'Content pre-fetch'),
        ('config_refresh', 'Experiment/config refresh'),
    ]
    STATUS_CHOICES = [
        ('queued', 'Queued'), ('sent', 'Sent'),
        ('no_devices', 'No active devices'), ('failed', 'Failed'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE,
                             related_name='silent_pushes')
    push_type = models.CharField(max_length=20, choices=PUSH_TYPE_CHOICES)
    data = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES,
                              default='queued', db_index=True)
    devices_sent = models.PositiveSmallIntegerField(default=0)
    error = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)


# ──────────────────────────────────────────────────────────────────────
# CH19 — Crash reporting (self-hosted Sentry-lite ingest)
# ──────────────────────────────────────────────────────────────────────

class CrashGroup(models.Model):
    """Crashes grouped by a normalised stack hash (like Sentry issues)."""
    STATUS_CHOICES = [
        ('open', 'Open'), ('resolved', 'Resolved'),
        ('ignored', 'Ignored'), ('regressed', 'Regressed'),
    ]

    stack_hash = models.CharField(max_length=64, unique=True)
    error_type = models.CharField(max_length=120)
    error_message = models.CharField(max_length=300, blank=True)
    platform = models.CharField(max_length=12, blank=True)
    first_app_version = models.CharField(max_length=24, blank=True)
    last_app_version = models.CharField(max_length=24, blank=True)
    events_count = models.PositiveIntegerField(default=0)
    users_affected = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES,
                              default='open', db_index=True)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'{self.error_type}: {self.error_message[:40]}'


class CrashEvent(models.Model):
    group = models.ForeignKey(CrashGroup, on_delete=models.CASCADE,
                              related_name='events')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                             blank=True, related_name='crash_events')
    device_fingerprint = models.CharField(max_length=64, blank=True)
    platform = models.CharField(max_length=12, blank=True)
    app_version = models.CharField(max_length=24, blank=True)
    os_version = models.CharField(max_length=24, blank=True)
    device_model = models.CharField(max_length=64, blank=True)
    stack_trace = models.TextField(blank=True)
    breadcrumbs = models.JSONField(default=list, blank=True)
    context = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)


# ──────────────────────────────────────────────────────────────────────
# CH20 — Mobile analytics event ingest (batched, base schema)
# ──────────────────────────────────────────────────────────────────────

class MobileAnalyticsEvent(models.Model):
    """One event with the full mobile base schema. ``event_id`` makes
    batch ingest idempotent (client retries never double-count).
    """
    event_id = models.UUIDField(unique=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                             blank=True, related_name='mobile_events')
    session_id = models.CharField(max_length=64, blank=True, db_index=True)
    device_fingerprint = models.CharField(max_length=64, blank=True, db_index=True)
    platform = models.CharField(max_length=12, blank=True)
    app_version = models.CharField(max_length=24, blank=True)
    os_version = models.CharField(max_length=24, blank=True)
    device_model = models.CharField(max_length=64, blank=True)
    network_type = models.CharField(max_length=12, blank=True)  # wifi/cellular/none
    locale = models.CharField(max_length=12, blank=True)
    ab_variants = models.JSONField(default=dict, blank=True)
    event_name = models.CharField(max_length=64, db_index=True)
    event_category = models.CharField(max_length=32, blank=True)
    properties = models.JSONField(default=dict, blank=True)
    event_time = models.DateTimeField(db_index=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['event_name', 'event_time'])]


class MobileEventBatch(models.Model):
    """Audit row per ingest batch (flushed every 30s / on background)."""
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                             blank=True, related_name='mobile_event_batches')
    device_fingerprint = models.CharField(max_length=64, blank=True)
    events_received = models.PositiveSmallIntegerField(default=0)
    events_accepted = models.PositiveSmallIntegerField(default=0)
    events_duplicate = models.PositiveSmallIntegerField(default=0)
    events_rejected = models.PositiveSmallIntegerField(default=0)
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)


# ──────────────────────────────────────────────────────────────────────
# CH21 — A/B testing: client-side flag evaluation config
# ──────────────────────────────────────────────────────────────────────

class MobileExperiment(models.Model):
    """Experiment config served to the app for *client-side* deterministic
    evaluation (FNV-1a hash of user+experiment, zero per-flag latency,
    offline-resilient). Complements apps.flags (server-side bucketing).
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'), ('running', 'Running'),
        ('paused', 'Paused'), ('concluded', 'Concluded'),
    ]

    slug = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=160)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES,
                              default='draft', db_index=True)
    traffic_allocation = models.PositiveSmallIntegerField(default=100)  # 0-100 %
    # [{"id": "control", "weight": 50, "config": {...}}, ...] weights sum to 100
    variants = models.JSONField(default=list)
    platform = models.CharField(max_length=12, default='all')  # all/ios/android
    min_app_version = models.CharField(max_length=24, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.slug


# ──────────────────────────────────────────────────────────────────────
# CH22 — Deferred deep links (install attribution → first-launch routing)
# ──────────────────────────────────────────────────────────────────────

class DeferredDeepLink(models.Model):
    """Share link tapped with no app installed → store target → after
    install + first launch the app claims it by fingerprint or token.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'), ('claimed', 'Claimed'), ('expired', 'Expired'),
    ]

    token = models.CharField(max_length=64, unique=True)
    device_fingerprint = models.CharField(max_length=64, blank=True, db_index=True)
    target_path = models.CharField(max_length=300)  # e.g. /product/123
    params = models.JSONField(default=dict, blank=True)
    campaign = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES,
                              default='pending', db_index=True)
    claimed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                   blank=True, related_name='claimed_deeplinks')
    claimed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)


# ──────────────────────────────────────────────────────────────────────
# CH24 — Releases, client perf metrics (RUM) and the KPI dashboard
# ──────────────────────────────────────────────────────────────────────

class AppRelease(models.Model):
    """One row per shipped release — feeds the per-release KPIs
    (JS bundle size, binary size) and the update-prompt endpoint.
    """
    platform = models.CharField(max_length=12)  # ios/android/web
    version = models.CharField(max_length=24)
    build_number = models.PositiveIntegerField(default=1)
    js_bundle_kb = models.PositiveIntegerField(default=0)    # gzip, target < 1536
    binary_size_mb = models.DecimalField(max_digits=6, decimal_places=1,
                                         default=0)          # target < 30
    rollout_pct = models.PositiveSmallIntegerField(default=100)
    is_mandatory = models.BooleanField(default=False)
    release_notes = models.TextField(blank=True)
    released_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('platform', 'version', 'build_number')]
        ordering = ['-released_at']


class ClientPerfMetric(models.Model):
    """RUM sample reported by the app (batched). Feeds cold-start p95,
    FPS p5 and API success-rate KPIs.
    """
    METRIC_CHOICES = [
        ('cold_start_ms', 'Cold start (ms)'),
        ('screen_render_ms', 'Screen render (ms)'),
        ('js_fps', 'JS thread FPS'),
        ('api_success', 'API request success (count)'),
        ('api_failure', 'API request failure (count)'),
        ('memory_mb', 'Memory (MB)'),
    ]

    metric = models.CharField(max_length=20, choices=METRIC_CHOICES, db_index=True)
    value = models.DecimalField(max_digits=12, decimal_places=2)
    platform = models.CharField(max_length=12, blank=True)
    app_version = models.CharField(max_length=24, blank=True)
    device_model = models.CharField(max_length=64, blank=True)
    device_class = models.CharField(max_length=8, blank=True)  # low/mid/high
    network_type = models.CharField(max_length=12, blank=True)
    screen = models.CharField(max_length=64, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                             blank=True, related_name='perf_metrics')
    device_fingerprint = models.CharField(max_length=64, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True, db_index=True)


class MobileKpiSnapshot(models.Model):
    """CH24 dashboard — one row per day with every KPI in the doc table."""
    snapshot_date = models.DateField(unique=True)
    cold_start_p95_ms = models.PositiveIntegerField(default=0)      # target < 2000
    js_fps_p5 = models.DecimalField(max_digits=5, decimal_places=1,
                                    default=0)                       # target > 55
    crash_rate_pct = models.DecimalField(max_digits=6, decimal_places=3,
                                         default=0)                  # target < 0.1
    api_success_pct = models.DecimalField(max_digits=5, decimal_places=2,
                                          default=0)                 # target > 99
    checkout_completion_pct = models.DecimalField(max_digits=5, decimal_places=2,
                                                  default=0)         # target > 65
    search_to_pdp_ctr_pct = models.DecimalField(max_digits=5, decimal_places=2,
                                                default=0)           # target > 25
    biometric_success_pct = models.DecimalField(max_digits=5, decimal_places=2,
                                                default=0)           # target > 95
    offline_sync_success_pct = models.DecimalField(max_digits=5, decimal_places=2,
                                                   default=0)        # target > 98
    dau = models.PositiveIntegerField(default=0)
    events_ingested = models.PositiveIntegerField(default=0)
    crash_groups_open = models.PositiveIntegerField(default=0)
    computed_at = models.DateTimeField(auto_now=True)


# ──────────────────────────────────────────────────────────────────────
# Append-only audit log ("every touch is logged in the DB")
# ──────────────────────────────────────────────────────────────────────

class MobileEngineeringEvent(models.Model):
    kind = models.CharField(max_length=48, db_index=True)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                              blank=True, related_name='mobile_eng_events')
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    @staticmethod
    def log(kind, actor=None, **payload):
        """Never raises — audit logging must not break the request path."""
        try:
            MobileEngineeringEvent.objects.create(
                kind=kind,
                actor=actor if getattr(actor, 'pk', None) else None,
                payload=payload,
            )
        except Exception:
            pass
