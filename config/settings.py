from celery.schedules import crontab
"""
MICHA — Production Settings v2
Fixes every gap identified in the 40-year senior engineer audit:
- Session backend → Redis
- DB connection pooling + statement timeout
- Proper cache config
- Float → Decimal for all financial fields
- Query timeout
- API versioning prefix
- Datetime format standardised
- All security headers
"""
from pathlib import Path
from datetime import timedelta
import os

BASE_DIR = Path(__file__).resolve().parent.parent


# ── Load .env file (pure Python, no dependencies) ─────────────────────────────
def _read_env():
    env_path = BASE_DIR / '.env'
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, val = line.partition('=')
                    os.environ.setdefault(key.strip(), val.strip())

_read_env()

# ── Core ──────────────────────────────────────────────────────────────────────
# SECRET_KEY MUST be set explicitly in production. The dev-default below is
# intentionally insecure-named so that a misconfigured deploy refuses to boot
# (the validate-on-boot check at the bottom of this module raises
# ImproperlyConfigured when DEBUG=False and the key still matches the default).
#
# Why this matters: SECRET_KEY signs JWTs, sessions, CSRF tokens, password-reset
# tokens, and the field-encryption seed. A leaked or default value means every
# user is impersonable and every encrypted DB column is decryptable.
_DEV_SECRET_KEY = 'django-insecure-dev-only-change-in-production'
SECRET_KEY = os.environ.get('SECRET_KEY', _DEV_SECRET_KEY)
DEBUG = os.environ.get('DEBUG', 'True') == 'True'
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1,0.0.0.0').split(',')
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:3000')
ADMIN_URL = os.environ.get('ADMIN_URL', 'admin/')

# ── Apps ──────────────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sitemaps',
    'django.contrib.postgres',
    'rest_framework',
    'rest_framework.authtoken',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'apps.ledger',
    'apps.outbox',
    'apps.risk',
    'apps.idempotency',
    'apps.webhooks',
    'apps.inbound_webhooks',
    'apps.sagas',
    'apps.data_rights',
    'apps.flags',
    'apps.fx',
    'apps.bulk_ops',
    'apps.dev_keys',
    'apps.tax',
    'apps.cases',
    'apps.loyalty',
    'apps.two_factor',
    'apps.alerts',
    'apps.content_safety',
    'apps.forecasting',
    'apps.feed',
    'apps.affiliates',
    'apps.gift_cards',
    'apps.imagery',
    'apps.waitlist',
    'apps.telemetry',
    'apps.users',
    'apps.verification',
    'apps.stores',
    'apps.products',
    'apps.cart',
    'apps.wishlist',
    'apps.ai_engine',
    'apps.orders',
    'apps.shipping',
    'apps.promotions',
    'apps.inventory',
    'apps.chat',
    'apps.notifications',
    'apps.accounts',
    'apps.reports',
    'apps.seller',
    'apps.listings',
    'apps.reviews',
    'apps.payments',
    'apps.trust',
    'apps.search',
    'apps.recommendations',
    'apps.collections',
    'apps.analytics',
    'apps.admin_actions',
    'apps.i18n',
    'apps.seo',
    'apps.admin_api',
    'apps.rentals',
    'apps.verification_gate',
    'apps.monitoring',
    'apps.core',
    'apps.security',
    'apps.disputes',
    'apps.moderation',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'middleware.logging_middleware.RequestIDMiddleware',
    # Edge rate limiter — runs EARLY so banned/over-band IPs are
    # rejected before any view dispatch or DB query happens. Slots in
    # AFTER RequestIDMiddleware so 429 responses carry a request_id for
    # incident correlation, but BEFORE all the heavyweight middleware.
    'middleware.rate_limiter.EdgeRateLimiterMiddleware',
    # Per-path DB statement_timeout. After the rate limiter so banned
    # IPs don't even cause a SET roundtrip; before view dispatch so the
    # tighter timeout applies to ALL queries the view runs.
    'middleware.db_timeout.PerPathStatementTimeoutMiddleware',
    'apps.telemetry.middleware.MetricsMiddleware',
    # QueryBudgetMiddleware OUTSIDE QueryAuditMiddleware so its response-
    # phase code runs AFTER query_audit sets request._db_queries.
    'middleware.query_budget.QueryBudgetMiddleware',
    'apps.telemetry.query_audit.QueryAuditMiddleware',
    # N+1 detector — runs INSIDE query_audit so it sees the same hook
    # state. Records SQL templates per request and warns when the same
    # template ran above N_PLUS_ONE_THRESHOLD times.
    'apps.telemetry.n_plus_one.NPlusOneMiddleware',
    'middleware.security_hardening.SecurityHardeningMiddleware',
    'middleware.security_hardening.FileUploadSecurityMiddleware',
    'middleware.terms_version.TermsVersionMiddleware',
    'middleware.sanitise.SanitiseInputMiddleware',
    'apps.verification_gate.middleware.SellerVerificationMiddleware',
    'apps.dev_keys.middleware.APIKeyUsageMiddleware',
    # Egress normalizer for the canonical error envelope. Positioned LAST
    # in the chain so its response phase runs FIRST — the DRF Response is
    # still un-rendered at this point, so mutating .data takes effect.
    # Moving it earlier means downstream middlewares (telemetry, etc.)
    # trigger .render() and lock the body before normalization runs.
    'middleware.error_envelope.ErrorEnvelopeMiddleware',
    # Auto-audit every successful mutating admin request. Manual
    # AdminActionLog.log() / @audit_admin_action still work — they
    # call mark_logged(request) to suppress this middleware for the
    # request so we don't double-log. This middleware is the safety
    # net for endpoints nobody remembered to instrument.
    'apps.admin_actions.middleware.AdminActionAuditMiddleware',
    # R3: per-request cost estimate. OFF in DEBUG (would spam dev
    # console), ON in prod. Emits a structured log line + Prometheus
    # counter labelled by route+method+status. Disabled by setting
    # COST_TELEMETRY_ENABLED=False.
    'middleware.cost_telemetry.CostTelemetryMiddleware',
]

CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [o.strip() for o in os.environ.get('CORS_ALLOWED_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(',') if o.strip()]
if not DEBUG:
    CORS_ALLOWED_ORIGINS = [o for o in os.environ.get('CORS_ALLOWED_ORIGINS', '').split(',') if o]

CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get('CORS_ALLOWED_ORIGINS', 'http://localhost:3000').split(',') if o]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [],
    'APP_DIRS': True,
    'OPTIONS': {
        'context_processors': [
            'django.template.context_processors.request',
            'django.contrib.auth.context_processors.auth',
            'django.contrib.messages.context_processors.messages',
        ]
    },
}]

WSGI_APPLICATION = 'config.wsgi.application'

try:
    ASGI_APPLICATION = 'config.asgi.application'
except Exception:
    pass

# ── Database ──────────────────────────────────────────────────────────────────
_REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

if os.environ.get('DB_NAME'):
    DATABASES = {
        'default': {
        'TEST': {
            'NAME': 'test_micha',
        },
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DB_NAME', ''),
            'USER': os.environ.get('DB_USER', 'postgres'),
            'PASSWORD': os.environ.get('DB_PASSWORD', ''),
            'HOST': os.environ.get('DB_HOST', 'localhost'),
            'PORT': os.environ.get('DB_PORT', '5432'),
            # FIX: Connection pooling — keep connections alive, don't open new one per request
            'CONN_MAX_AGE': int(os.environ.get('DB_CONN_MAX_AGE', 60)),
            'CONN_HEALTH_CHECKS': True,
            'OPTIONS': {
                'connect_timeout': 10,
                # Three timeouts protect the pool from runaway / wedged code:
                #   statement_timeout                  — kill any single query > 30s
                #   lock_timeout                       — kill a query waiting > 5s on a row lock
                #   idle_in_transaction_session_timeout — kill a tx that's been open > 60s
                # Without these, a single bug (forgotten commit, long
                # SELECT FOR UPDATE) wedges the entire connection pool.
                'options': (
                    '-c statement_timeout=30000'
                    ' -c lock_timeout=5000'
                    ' -c idle_in_transaction_session_timeout=60000'
                ),
            },
        }
    }
else:
    DATABASES = {
        'default': {
        'TEST': {
            'NAME': 'test_micha',
        },
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# R3: Read replica routing.
# When DB_REPLICA_HOST is set in env, register a 'replica' database
# alias and activate the router. Analytics / search / recommendations
# / collections / reviews / i18n / seo reads route to the replica;
# financial / auth-critical apps (payments / orders / users / etc.)
# stay on primary. Writes always go to primary.
#
# Safe default: when DB_REPLICA_HOST is unset, the router is NOT
# registered. db_router.ReadReplicaRouter is also defensive — if
# 'replica' isn't in DATABASES at runtime, all reads route to default.
if os.environ.get('DB_REPLICA_HOST'):
    DATABASES['replica'] = {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_REPLICA_NAME', os.environ.get('DB_NAME', '')),
        'USER': os.environ.get('DB_REPLICA_USER', os.environ.get('DB_USER', 'postgres')),
        'PASSWORD': os.environ.get('DB_REPLICA_PASSWORD', os.environ.get('DB_PASSWORD', '')),
        'HOST': os.environ.get('DB_REPLICA_HOST'),
        'PORT': os.environ.get('DB_REPLICA_PORT', '5432'),
        'CONN_MAX_AGE': int(os.environ.get('DB_CONN_MAX_AGE', 60)),
        'CONN_HEALTH_CHECKS': True,
        'OPTIONS': {
            'connect_timeout': 10,
            'options': (
                '-c statement_timeout=30000'
                ' -c lock_timeout=5000'
                ' -c idle_in_transaction_session_timeout=60000'
            ),
        },
    }
    DATABASE_ROUTERS = ['config.db_router.ReadReplicaRouter']

AUTH_USER_MODEL = 'users.User'

# ── DRF ───────────────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'apps.dev_keys.auth.APIKeyAuthentication',
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    # FIX: Enforce standard pagination on ALL list endpoints
    'DEFAULT_PAGINATION_CLASS': 'middleware.pagination.StandardPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    # DRF DEFAULT_THROTTLE_RATES.
    #
    # PRIOR BUG: this dict had duplicate keys ('login', 'register', 'otp')
    # with conflicting values. Python's dict literal silently kept the
    # LAST value per key, so the table was effectively:
    #   login=10/minute, register=5/minute, otp=5/minute
    # The intent of the earlier (forgiving) values was unrecoverable;
    # the surviving aggressive values are what the security view set
    # actually relies on (apps/users/views.py uses LoginThrottle +
    # OTPThrottle on auth endpoints). De-duplicated here to keep the
    # table truthful.
    'DEFAULT_THROTTLE_RATES': {
        # Broad bands — apply to authenticated/anonymous traffic by
        # default. Aggressive vs DDoS but not vs a real human shopping.
        'anon': '10000/hour',
        'user': '10000/hour',

        # Auth / OTP — the rates that actually win after dedup.
        'login':       '10/minute',
        'register':    '5/minute',
        'otp':         '5/minute',
        'otp_verify':  '5/hour',

        # Endpoint-specific scopes (used by view-local Throttle classes).
        'payment':     '20/hour',
        'search':      '60/minute',
        'upload':      '20/hour',

        # Edge guard (middleware/rate_limiter.py) — burst and sustained
        # bands enforced at the request middleware layer, BEFORE any
        # DRF processing. These compose with the DRF throttles above:
        # the middleware shields against IP-scale floods; DRF still
        # gates per-user / per-endpoint behaviour for everything that
        # passes the middleware band.
        'anon_burst':     '30/minute',
        'anon_sustained': '200/hour',
    },
    'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer'],
    'EXCEPTION_HANDLER': 'middleware.exception_handler.custom_exception_handler',
    # FIX: Standardise datetime format across all endpoints
    'DATETIME_FORMAT': '%Y-%m-%dT%H:%M:%SZ',
    'DATE_FORMAT': '%Y-%m-%d',
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ── i18n ──────────────────────────────────────────────────────────────────────
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ── Static & Media ────────────────────────────────────────────────────────────
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

if os.environ.get('AWS_STORAGE_BUCKET_NAME'):
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    STATICFILES_STORAGE = 'storages.backends.s3boto3.S3StaticStorage'
    AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = os.environ.get('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_REGION_NAME = os.environ.get('AWS_S3_REGION_NAME', 'us-east-1')
    AWS_DEFAULT_ACL = 'private'
    AWS_S3_OBJECT_PARAMETERS = {'CacheControl': 'max-age=86400'}
    _cf = os.environ.get('AWS_CLOUDFRONT_DOMAIN', '')
    AWS_S3_CUSTOM_DOMAIN = _cf or f"{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com"
    MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/media/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── Email ─────────────────────────────────────────────────────────────────────
if os.environ.get('EMAIL_HOST'):
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = os.environ.get('EMAIL_HOST', '')
    EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
    EMAIL_USE_TLS = True
    EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
    EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
else:
    EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
DEFAULT_FROM_EMAIL = 'MICHA <noreply@micha.app>'

# T&C version — bump this to force all users to re-accept
CURRENT_TC_VERSION = os.environ.get('CURRENT_TC_VERSION', '1.0')

# Currency enforcement — T&C §5.4
ALLOWED_CURRENCIES = ['AOA']
DEFAULT_CURRENCY = 'AOA'

# ── Redis + Celery ────────────────────────────────────────────────────────────
REDIS_URL = _REDIS_URL
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
# FIX: Tasks only acknowledged after completion — no lost tasks on worker crash
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_REJECT_ON_WORKER_LOST = True
# FIX: Dead letter queue — failed tasks go here instead of silently disappearing
# R3 fix: there was a stray ``'TEST': {'NAME': 'test_micha'}`` block
# embedded INSIDE the 'default' queue dict — copy-paste of a DATABASES
# fragment that ended up here. Celery silently accepted the garbage
# (it ignores unknown keys), but it polluted the routing dict shape.
# Removed.
#
# R3: queue separation. webhooks / media / nightly added so a slow
# image-resize task doesn't block a payment-confirmation push.
CELERY_TASK_QUEUES = {
    'high':        {'exchange': 'high',        'routing_key': 'high'},
    'default':     {'exchange': 'default',     'routing_key': 'default'},
    'low':         {'exchange': 'low',         'routing_key': 'low'},
    'webhooks':    {'exchange': 'webhooks',    'routing_key': 'webhooks'},
    'media':       {'exchange': 'media',       'routing_key': 'media'},
    'nightly':     {'exchange': 'nightly',     'routing_key': 'nightly'},
    'ai_heavy':    {'exchange': 'ai_heavy',    'routing_key': 'ai_heavy'},
    'dead_letter': {'exchange': 'dead_letter', 'routing_key': 'dead_letter'},
}
CELERY_TASK_DEFAULT_QUEUE = 'default'
CELERY_TASK_ROUTES = {
    # Hot money paths — must drain fast. Worker pool size = high.
    'orders.*':        {'queue': 'high'},
    'payments.*':      {'queue': 'high'},
    'notifications.*': {'queue': 'high'},

    # Outbound webhooks — sellers' integrations expect us to fire fast
    # OR retry. Separate queue so a slow webhook target doesn't block
    # in-process notifications.
    'webhooks.*':      {'queue': 'webhooks'},
    'outbox.*':        {'queue': 'webhooks'},

    # Image processing — slow + CPU heavy, run on its own pool so it
    # never starves the high queue.
    'media.*':         {'queue': 'media'},
    'products.image_*': {'queue': 'media'},

    # Long-running reports / exports / nightly aggregates.
    'analytics.*':     {'queue': 'nightly'},
    'collections.record_price_history': {'queue': 'nightly'},
    'recommendations.weekly_digest':    {'queue': 'nightly'},
    'recommendations.recalculate_similarity': {'queue': 'nightly'},
    'ai_engine.embed_all_products_nightly': {'queue': 'ai_heavy'},
}
CELERY_BEAT_SCHEDULE = {

    # ── R6: Data retention enforcement ───────────────────────
    # Nightly purge of rows past their retention window. The policy
    # itself lives in apps.data_rights.retention; tweak via
    # DATA_RETENTION_POLICY in settings.
    'enforce-data-retention-nightly': {
        'task': 'data_rights.enforce_retention',
        'schedule': crontab(hour=3, minute=15),
        'options': {'queue': 'nightly'},
    },

    # ── R7: Email lifecycle ───────────────────────────────────
    # Each fires once per day at a staggered time so SES isn't
    # bursted. Disable globally via EMAIL_LIFECYCLE_ENABLED=False.
    'lifecycle-welcome': {
        'task': 'notifications.lifecycle_welcome',
        'schedule': crontab(hour=8, minute=0),
        'options': {'queue': 'nightly'},
    },
    'lifecycle-engagement-nudge': {
        'task': 'notifications.lifecycle_engagement',
        'schedule': crontab(hour=8, minute=15),
        'options': {'queue': 'nightly'},
    },
    'lifecycle-winback': {
        'task': 'notifications.lifecycle_winback',
        'schedule': crontab(hour=8, minute=30),
        'options': {'queue': 'nightly'},
    },
    'lifecycle-reactivation': {
        'task': 'notifications.lifecycle_reactivation',
        'schedule': crontab(hour=8, minute=45),
        'options': {'queue': 'nightly'},
    },

    # ── Users ─────────────────────────────────────────────────
    'cleanup-expired-otps': {
        'task': 'users.cleanup_expired_otps',
        'schedule': 3600,  # hourly
        'options': {'queue': 'default'},
    },
    'cleanup-old-activity-logs': {
        'task': 'users.cleanup_old_activity_logs',
        'schedule': 86400,  # daily
        'options': {'queue': 'low'},
    },
    'dormant-user-winback': {
        'task': 'users.dormant_user_winback',
        'schedule': crontab(hour=11, minute=0, day_of_week='sunday'),
        'options': {'queue': 'low'},
    },
    'delete-scheduled-accounts': {
        'task': 'users.delete_scheduled_accounts',
        'schedule': 86400,
        'options': {'queue': 'default'},
    },

    # ── Idempotency ───────────────────────────────────────────
    'sweep-expired-idempotency-keys': {
        'task': 'idempotency.sweep_expired',
        'schedule': 3600,  # hourly — 24h TTL, no need to be aggressive
        'options': {'queue': 'low'},
    },

    # ── Webhooks ──────────────────────────────────────────────
    'sweep-webhook-retries': {
        'task': 'webhooks.sweep_retries',
        'schedule': 60,  # every minute — picks up due retries fast
        'options': {'queue': 'default'},
    },

    # ── Sagas ─────────────────────────────────────────────────
    'advance-waiting-sagas': {
        'task': 'sagas.advance_waiting',
        'schedule': 60,
        'options': {'queue': 'default'},
    },
    'abandon-overdue-sagas': {
        'task': 'sagas.abandon_overdue',
        'schedule': 300,  # every 5 min
        'options': {'queue': 'default'},
    },
    'reap-abandoned-checkouts': {
        'task': 'sagas.reap_abandoned_checkouts',
        'schedule': 600,  # every 10 min — grace=30min by default
        'options': {'queue': 'default'},
    },

    # ── Bulk operations ──────────────────────────────────────
    'drive-pending-bulk-jobs': {
        'task': 'bulk_ops.drive_pending',
        'schedule': 60,  # belt-and-braces — picks up jobs that lost their .delay()
        'options': {'queue': 'low'},
    },

    # ── Loyalty ───────────────────────────────────────────────
    'recompute-loyalty-tiers': {
        'task': 'loyalty.recompute_all_tiers',
        'schedule': 86400,  # nightly — beat-fired with singleton_task guard
        'options': {'queue': 'low'},
    },

    # ── Alerts ────────────────────────────────────────────────
    'run-saved-searches': {
        'task': 'alerts.run_saved_searches',
        'schedule': 3600,  # hourly — bounded by per-row min_notify_interval
        'options': {'queue': 'low'},
    },

    # ── Forecasting ───────────────────────────────────────────
    'run-forecasting': {
        'task': 'forecasting.run_all',
        'schedule': 86400,  # nightly per-product forecast + reorder check
        'options': {'queue': 'low'},
    },

    # ── Gift cards ───────────────────────────────────────────
    'gift-cards-expire-overdue': {
        'task': 'gift_cards.expire_overdue',
        'schedule': 86400,  # daily — sweeps expired cards with positive balance
        'options': {'queue': 'low'},
    },

    # ── Waitlist ──────────────────────────────────────────────
    'waitlist-drain-pending': {
        'task': 'waitlist.drain_pending',
        'schedule': 60,  # every minute — catches signal-bypass restocks
        'options': {'queue': 'default'},
    },
    'waitlist-cleanup-stale': {
        'task': 'waitlist.cleanup_stale',
        'schedule': 86400,
        'options': {'queue': 'low'},
    },

    # ── Promotions / Coupons ──────────────────────────────────
    'coupons-cleanup-expired': {
        'task': 'promotions.coupons_cleanup_expired',
        'schedule': 86400,  # daily — soft-deactivate past-window coupons
        'options': {'queue': 'low'},
    },

    # ── Security ──────────────────────────────────────────────
    'security-purge-old-login-attempts': {
        'task': 'security.purge_old_login_attempts',
        'schedule': 86400,  # daily — purge LoginAttempt past retention window
        'options': {'queue': 'low'},
    },

    # ── Outbox DLQ health ─────────────────────────────────────
    # Refresh the dead-count + stale-retry gauges every 5 min so
    # Prometheus has a real signal to alert on. Without this, the
    # gauges sit at their last-seen value forever.
    'outbox-refresh-dlq-metrics': {
        'task': 'outbox.refresh_dlq_metrics',
        'schedule': 300,
        'options': {'queue': 'low'},
    },

    # ── Ledger reconciliation ─────────────────────────────────
    # Global invariant check: Σ debits == Σ credits. Cheap, runs every
    # 5 min so any drift is alertable within a minute.
    'ledger-check-invariants': {
        'task': 'ledger.check_invariants',
        'schedule': 300,
        'options': {'queue': 'low'},
    },
    # Hourly cached-counter scan: User.store_credit, loyalty_points,
    # SellerWallet.balance vs ledger truth. Surfaces drift to gauges +
    # admin endpoint; does NOT auto-correct (operator decision).
    'ledger-reconcile-cached': {
        'task': 'ledger.reconcile_cached',
        'schedule': 3600,
        'options': {'queue': 'low'},
    },

    # ── Inbound webhooks ──────────────────────────────────────
    # Refresh failure-rate gauge every 5 min for fast incident detection.
    'inbound-webhooks-refresh-metrics': {
        'task': 'inbound_webhooks.refresh_metrics',
        'schedule': 300,
        'options': {'queue': 'low'},
    },
    # Daily retention purge — keeps GDPR-bound IP/UA data bounded.
    'inbound-webhooks-purge-old': {
        'task': 'inbound_webhooks.purge_old',
        'schedule': 86400,
        'options': {'queue': 'low'},
    },

    # ── Affiliates ────────────────────────────────────────────
    'affiliates-confirm-pending': {
        'task': 'affiliates.confirm_pending',
        'schedule': 3600,  # hourly — moves pending → confirmed past hold
        'options': {'queue': 'low'},
    },
    'affiliates-process-payouts': {
        'task': 'affiliates.process_payouts',
        'schedule': 86400,  # nightly
        'options': {'queue': 'low'},
    },

    # ── Cart ──────────────────────────────────────────────────
    'cart-abandonment-nudge': {
        # R5: rewritten task — see apps/cart/tasks.py docstring for
        # the pre-R5 bug history (broken field names + no push delivery
        # + spammy dedup). Hourly cadence aligned with the 24h per-cart
        # re-ping interval; running more often just wastes worker
        # cycles without sending more pushes.
        'task': 'cart.send_abandonment_nudge',
        'schedule': 3600,  # every hour
        'options': {'queue': 'default'},
    },

    # ── Orders ────────────────────────────────────────────────
    'auto-complete-old-orders': {
        'task': 'orders.auto_complete_old_orders',
        'schedule': 3600,
        'options': {'queue': 'default'},
    },
    'release-order-escrow': {
        'task': 'orders.release_order_escrow',
        'schedule': 3600,
        'options': {'queue': 'high'},
    },
    'enforce-return-deadlines': {
        'task': 'orders.enforce_return_deadlines',
        'schedule': 1800,  # every 30 min — SLA windows are in hours/days
        'options': {'queue': 'default'},
    },

    # ── Payments ──────────────────────────────────────────────
    'release-held-earnings': {
        'task': 'payments.release_held_earnings',
        'schedule': 3600,
        'options': {'queue': 'high'},
    },
    'auto-payout-sellers': {
        'task': 'payments.auto_payout_sellers',
        'schedule': crontab(hour=9, minute=0, day_of_week='monday'),
        'options': {'queue': 'high'},
    },

    # ── Recommendations & AI ──────────────────────────────────
    'precompute-user-feeds': {
        'task': 'recommendations.precompute_user_feeds',
        'schedule': 1800,
        'options': {'queue': 'low'},
    },
    'check-price-alerts': {
        'task': 'recommendations.check_price_alerts',
        'schedule': 1800,
        'options': {'queue': 'default'},
    },
    'check-back-in-stock': {
        'task': 'recommendations.check_back_in_stock_alerts',
        'schedule': 900,  # every 15 min
        'options': {'queue': 'default'},
    },
    'cleanup-stock-urgency': {
        'task': 'recommendations.cleanup_stock_urgency',
        'schedule': 300,  # every 5 min
        'options': {'queue': 'low'},
    },
    'recalculate-product-similarity': {
        'task': 'recommendations.recalculate_product_similarity',
        'schedule': crontab(hour=3, minute=0),  # 3am daily
        'options': {'queue': 'low'},
    },
    'recompute-search-query-boosts': {
        'task': 'search.recompute_query_boosts',
        'schedule': 3600,  # hourly — picks up recent clicks/purchases
        'options': {'queue': 'low'},
    },
    'send-weekly-digest': {
        'task': 'recommendations.send_weekly_digest',
        'schedule': crontab(hour=10, minute=0, day_of_week='friday'),
        'options': {'queue': 'low'},
    },
    'check-all-price-drops': {
        'task': 'ai_engine.check_all_price_drops',
        'schedule': 3600,
        'options': {'queue': 'default'},
    },
    'embed-all-products-nightly': {
        'task': 'ai_engine.embed_all_products_nightly',
        'schedule': crontab(hour=2, minute=0),
        'options': {'queue': 'low'},
    },
    'refresh-stale-recommendation-caches': {
        'task': 'ai_engine.refresh_stale_recommendation_caches',
        'schedule': 1800,
        'options': {'queue': 'low'},
    },

    # ── Inventory ─────────────────────────────────────────────
    'clean-expired-reservations': {
        'task': 'inventory.clean_expired_reservations',
        'schedule': 300,
        'options': {'queue': 'default'},
    },
    'send-low-stock-alerts': {
        'task': 'inventory.send_low_stock_alerts',
        'schedule': crontab(hour=8, minute=0),
        'options': {'queue': 'default'},
    },

    # ── Verification ──────────────────────────────────────────
    'suspend-expired-kyc': {
        'task': 'verification.suspend_expired_kyc',
        'schedule': crontab(hour=0, minute=0),
        'options': {'queue': 'default'},
    },
    'send-selfie-reminders': {
        'task': 'verification.send_selfie_reminders',
        'schedule': crontab(hour=9, minute=0),
        'options': {'queue': 'default'},
    },
    'verification-daily-check': {
        'task': 'verification_gate.daily_verification_check',
        'schedule': 86400,
        'options': {'queue': 'default'},
    },

    # ── Analytics ─────────────────────────────────────────────
    'update-seller-performance-scores': {
        'task': 'analytics.update_seller_performance_scores',
        'schedule': crontab(hour='*/6', minute=0),  # every 6h
        'options': {'queue': 'low'},
    },
    'cleanup-old-funnel-events': {
        'task': 'analytics.cleanup_old_funnel_events',
        'schedule': crontab(hour=1, minute=0),
        'options': {'queue': 'low'},
    },
    'record-price-history': {
        'task': 'collections.record_price_history',
        'schedule': crontab(hour=0, minute=30),
        'options': {'queue': 'low'},
    },

    # ── Trust & Fraud ─────────────────────────────────────────
    'fraud-sweep': {
        'task': 'trust.run_fraud_sweep',
        'schedule': crontab(hour=4, minute=0),
        'options': {'queue': 'default'},
    },
    'recompute-all-trust-scores': {
        'task': 'trust.recompute_all_trust_scores',
        'schedule': crontab(hour=5, minute=0),
        'options': {'queue': 'low'},
    },

    # ── Payment Reconciliation ────────────────────────────────
    'payment-reconciliation': {
        'task': 'payments.run_payment_reconciliation',
        'schedule': crontab(hour=2, minute=0),  # 2am daily
        'options': {'queue': 'high'},
    },

    # ── Refund pipeline (commits 36baec1, 9aa8879, NN) ───────
    #
    # Three tasks form the refund-correctness loop:
    #
    #  1. process-pending-refunds  — drains Refund(status='pending')
    #     rows through the gateway. Runs every 2 minutes for tight
    #     turnaround on disputes / buyer requests / return flows.
    #
    #  2. reconcile-refunds        — detects drift where the gateway
    #     refunded but our local atomic block didn't catch up (the
    #     "wallet didn't debit but card was credited" residual gap
    #     left by gateway-first ordering). Idempotent at every layer
    #     so 5-minute cadence is harmless; runs scoped to last 72h.
    #
    #  3. payment-reconciliation   — pre-existing daily sweep that
    #     reconciles ALL pending Payment rows against the gateway
    #     (handles missed webhooks). Refund-specific drift is faster
    #     to find via the dedicated task above.
    #
    # All three are queue='high' because refund delay = buyer
    # complaint = chargeback = much-more-expensive failure.

    'process-pending-refunds': {
        'task': 'payments.process_pending_refunds',
        'schedule': 120,  # every 2 minutes
        'options': {'queue': 'high'},
    },
    'reconcile-refunds': {
        'task': 'payments.reconcile_refunds',
        'schedule': 300,  # every 5 minutes
        'options': {'queue': 'high'},
    },

    # ── FX (foreign exchange) ────────────────────────────────
    # Hourly: pull latest rates from BNA / external feeds via the
    # drift-guarded update_rate path. Blocked drifts are logged for
    # ops triage — they're NOT auto-overridden because a 30% jump on
    # a feed could be either a real devaluation or a broken upstream.
    'fx-refresh-rates': {
        'task': 'fx.refresh_rates',
        'schedule': 3600,
        'options': {'queue': 'default'},
    },
    # Every 30 min: warn (+ metric) on any current rate past
    # FX_MAX_AGE_HOURS. Without this nobody notices a silently-broken
    # refresh worker — and stale rates are money-correctness bugs.
    'fx-check-staleness': {
        'task': 'fx.check_staleness',
        'schedule': 1800,
        'options': {'queue': 'low'},
    },

    # ── Disputes ──────────────────────────────────────────────
    # SLA sweep auto-resolves disputes where the seller has gone
    # silent past auto_resolve_at (refund_buyer) OR escalates to
    # under_review if the seller responded but no admin decision
    # landed. Without this task, the dispute commit (3812522) is
    # decorative — disputes sit open forever and NPS tanks.
    'disputes-sweep-sla': {
        'task': 'disputes.sweep_dispute_sla',
        'schedule': crontab(minute='17'),  # hourly at :17 (off-the-hour to spread load)
        'options': {'queue': 'default'},
    },

    # ── AI Feed Quality ───────────────────────────────────────
    'feed-quality-report': {
        'task': 'ai_engine.check_all_price_drops',  # reuse existing task runner
        'schedule': crontab(hour=6, minute=0),  # 6am daily report
        'options': {'queue': 'low'},
    },

    # ── Seller ────────────────────────────────────────────────
    'seller-engagement-nudge': {
        'task': 'seller.seller_engagement_nudge',
        'schedule': crontab(hour=9, minute=0, day_of_week='monday'),
        'options': {'queue': 'low'},
    },
}

# ── Cache — Redis in prod, LocMem in dev ──────────────────────────────────────
CACHES = {
    'default': {
        'TEST': {
            'NAME': 'test_micha',
        },
        'BACKEND': 'django.core.cache.backends.redis.RedisCache' if os.environ.get('REDIS_URL') else 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': REDIS_URL if os.environ.get('REDIS_URL') else '',
        'KEY_PREFIX': 'micha',
        'TIMEOUT': 300,
    }
}

# FIX: Session backend → Redis (not DB!)
# DB-backed sessions create a read on the sessions table for EVERY request
# This single table becomes the bottleneck under load
if os.environ.get('REDIS_URL'):
    SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
    SESSION_CACHE_ALIAS = 'default'
else:
    SESSION_ENGINE = 'django.contrib.sessions.backends.db'

SESSION_COOKIE_AGE = 86400 * 7
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

# ── Channels ──────────────────────────────────────────────────────────────────
# FIX: InMemoryChannelLayer does NOT work across multiple processes
# Even in dev, use Redis if available so behaviour matches production
CHANNEL_LAYERS = {
    'default': {
        'TEST': {
            'NAME': 'test_micha',
        },
        'BACKEND': 'channels_redis.core.RedisChannelLayer' if os.environ.get('REDIS_URL') else 'channels.layers.InMemoryChannelLayer',
        'CONFIG': {'hosts': [REDIS_URL]} if os.environ.get('REDIS_URL') else {},
    }
}

# ── Security ──────────────────────────────────────────────────────────────────
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

if not DEBUG:
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_SSL_REDIRECT = os.environ.get("FORCE_HTTPS", "false").lower() == "true"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# Image resize variants (created on upload)
IMAGE_SIZES = {
    'thumbnail': (200, 200),
    'medium': (400, 400),
    'large': (800, 800),
}
ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/gif']
ALLOWED_VIDEO_TYPES = ['video/mp4', 'video/quicktime', 'video/webm']
ALLOWED_DOC_TYPES = ['application/pdf', 'image/jpeg', 'image/png']

# ── App constants ─────────────────────────────────────────────────────────────
BANNED_KEYWORDS = ['weapon', 'explosive', 'drug', 'scam', 'fake', 'counterfeit', 'illegal']
SELLER_HOLD_DAYS = 7
PLATFORM_COMMISSION_DEFAULT = 5.0
LOYALTY_POINTS_PER_PURCHASE = 10
LOYALTY_REFERRAL_REWARD = 100
LOYALTY_REFERRED_REWARD = 50
PRICE_HISTORY_RETENTION_DAYS = 90
OTP_MAX_ATTEMPTS = 5
STORE_TIMEZONE = 'Africa/Luanda'  # Angola is UTC+1

# Data retention policies (days)
DATA_RETENTION = {
    'browsing_sessions': 30,
    'stock_urgency_signals': 1,
    'funnel_events': 365,
    'activity_logs': 365,
    'search_history': 90,
}

# ── External services ─────────────────────────────────────────────────────────
FIREBASE_CREDENTIALS_PATH = os.environ.get('FIREBASE_CREDENTIALS_PATH', '')
SENTRY_DSN = os.environ.get('SENTRY_DSN', '')
FIELD_ENCRYPTION_KEY = os.environ.get('FIELD_ENCRYPTION_KEY', '')
FLUTTERWAVE_SECRET_HASH = os.environ.get('FLUTTERWAVE_SECRET_HASH', '')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
APPLE_CLIENT_ID = os.environ.get('APPLE_CLIENT_ID', '')

# ── Sentry ────────────────────────────────────────────────────────────────────
# send_default_pii=False is necessary but NOT sufficient — it strips
# Django defaults (cookies, body, user) but log breadcrumbs, extra=
# kwargs, exception messages, stacktrace frame locals, and transaction
# URLs all carry PII unless we explicitly scrub. before_send delegates
# to middleware/sentry_scrub.py which reuses the PII redactor
# (middleware/pii_redactor.py) so the same scrub rules apply to errors
# and traces as to log lines.
if SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.redis import RedisIntegration
        from middleware.sentry_scrub import (
            before_send as _sentry_before_send,
            before_send_transaction as _sentry_before_send_tx,
        )
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            integrations=[DjangoIntegration(), CeleryIntegration(), RedisIntegration()],
            traces_sample_rate=0.1,
            send_default_pii=False,
            before_send=_sentry_before_send,
            before_send_transaction=_sentry_before_send_tx,
        )
    except ImportError:
        pass

# ── Logging ───────────────────────────────────────────────────────────────────
# ── Logging ─────────────────────────────────────────────────────
LOG_FORMAT = os.environ.get('LOG_FORMAT', 'json')  # 'json' or 'text'

# Master switch for the PII redactor in middleware/pii_redactor.py.
# Default ON: every JSON log line is scrubbed for emails, phone numbers,
# Bearer tokens, OTP-shape digit runs, and credential-named extra keys.
# Set to '0' in dev only if redaction is interfering with debugging —
# never turn off in production.
LOG_PII_REDACTION_ENABLED = os.environ.get('LOG_PII_REDACTION_ENABLED', '1') != '0'

# ── Image upload security (middleware/image_security.py) ─────────
# Tune from upload telemetry. Defaults are conservative for a
# marketplace at scale: product photos rarely need to exceed 12k px
# on a side or 50 MP total; avatars are 300px square.
IMAGE_MAX_FILE_BYTES    = int(os.environ.get('IMAGE_MAX_FILE_BYTES', 10 * 1024 * 1024))
IMAGE_MAX_PIXELS        = int(os.environ.get('IMAGE_MAX_PIXELS', 50_000_000))
IMAGE_MAX_DIMENSION     = int(os.environ.get('IMAGE_MAX_DIMENSION', 12_000))
IMAGE_MIN_ASPECT_RATIO  = float(os.environ.get('IMAGE_MIN_ASPECT_RATIO', '0.1'))
IMAGE_MAX_FRAMES        = int(os.environ.get('IMAGE_MAX_FRAMES', 50))

# ── FX rate hardening (apps/fx/service.py) ────────────────────
# Fat-finger guard on rate updates. A proposed rate that differs from
# the current rate by more than this percent is REJECTED unless the
# caller passes force=True. AOA has had ~50% devaluations in a day
# during crisis periods, so this is "fat-finger cap" not "policy
# ceiling" — operators force=True for legitimate large moves.
FX_MAX_DRIFT_PERCENT = os.environ.get('FX_MAX_DRIFT_PERCENT', '25')

# Staleness threshold for the current rate of any pair. Rates move
# daily-ish; 36h is "let an ops outage finish without alert spam" plus
# "alert if the refresh worker has been silently broken".
FX_MAX_AGE_HOURS = int(os.environ.get('FX_MAX_AGE_HOURS', '36'))

# Pairs the refresh worker pulls each hour. AOA-centric default; expand
# as the marketplace adds cross-border SKUs.
FX_REFRESH_PAIRS = [
    ('USD', 'AOA'), ('AOA', 'USD'),
    ('EUR', 'AOA'), ('AOA', 'EUR'),
    ('BRL', 'AOA'), ('AOA', 'BRL'),
]

# ── Inbound webhook hardening (apps/inbound_webhooks/) ────────
# Per-webhook body cap. Providers send small JSON; anything larger
# is almost certainly an attack. 64 KB is generous for normal traffic.
WEBHOOK_MAX_BODY_BYTES = int(os.environ.get('WEBHOOK_MAX_BODY_BYTES', 64 * 1024))

# Source-IP allowlist per provider (defence-in-depth — signature
# verification remains the primary control). Empty / missing entry
# disables IP enforcement for that provider. Populate from each
# provider's published egress IP ranges.
#
# Example (real IPs go in via env in prod):
#   WEBHOOK_ALLOWED_IPS = {
#       'appypay': ['41.220.x.y', '102.165.a.b'],
#       'stripe':  ['54.187.174.169', '54.187.205.235'],
#   }
WEBHOOK_ALLOWED_IPS = {}

# Strong-mode AppyPay signing: bind the timestamp into the HMAC input
# (Stripe-style). Default False for back-compat with the legacy
# body-only signature; flip to True once AppyPay's signing
# implementation supports timestamp binding. When True, a leaked
# secret bounds the forgery window to 5 minutes (DEFAULT_MAX_TIMESTAMP_AGE).
APPYPAY_REQUIRE_TIMESTAMP = os.environ.get('APPYPAY_REQUIRE_TIMESTAMP', '0') == '1'

# ── Outbox DLQ alerting (apps/outbox/tasks.py:refresh_dlq_metrics) ───
# Severity escalation thresholds for the periodic DLQ health check.
#
# When ANY of these trips, the periodic check logs CRITICAL — which
# the production logging pipeline (Datadog / CloudWatch / Loki) is
# expected to route to PagerDuty / Slack via a rule like:
#
#     severity=CRITICAL AND logger=outbox.*  →  page on-call
#
# Tune carefully:
#   • Too low: alert fatigue.
#   • Too high: real outages go unnoticed until manual review.
OUTBOX_DLQ_CRITICAL_DEAD_COUNT       = int(
    os.environ.get('OUTBOX_DLQ_CRITICAL_DEAD_COUNT', '10')
)
OUTBOX_DLQ_CRITICAL_OLDEST_AGE       = int(
    os.environ.get('OUTBOX_DLQ_CRITICAL_OLDEST_AGE', '3600')   # 1h
)
OUTBOX_DLQ_CRITICAL_STALE_RETRYING   = int(
    os.environ.get('OUTBOX_DLQ_CRITICAL_STALE_RETRYING', '5')
)

# ── Search input hardening (apps/search/safe_query.py) ────────
# Caps applied at sanitize_query / tokenize_safe time. The defaults are
# conservative for a marketplace search: longer queries don't return
# better results in practice and the cost of permissive limits is
# pathological-input vulnerability.
SEARCH_MAX_QUERY_CHARS = int(os.environ.get('SEARCH_MAX_QUERY_CHARS', '80'))
SEARCH_MAX_TOKENS      = int(os.environ.get('SEARCH_MAX_TOKENS', '10'))
SEARCH_MAX_TOKEN_CHARS = int(os.environ.get('SEARCH_MAX_TOKEN_CHARS', '40'))
SEARCH_MIN_TOKEN_CHARS = int(os.environ.get('SEARCH_MIN_TOKEN_CHARS', '2'))

# ── SES bounce / complaint webhook (apps/notifications/ses_webhook.py) ──
# Escape hatch for dev / staging when cryptography isn't installed AND
# no IP allowlist is configured. NEVER set this True in production —
# unauthenticated, unverified bounce/complaint events let an attacker
# suppress any address by spoofing an SNS-shaped payload.
SES_WEBHOOK_INSECURE = os.environ.get('SES_WEBHOOK_INSECURE', '0') == '1'

# ── Edge rate limiter (middleware/rate_limiter.py) ───────────
# Master switch. Disable in dev / tests where the burst band would
# fire on rapid request loops.
RATE_LIMITER_ENABLED = os.environ.get('RATE_LIMITER_ENABLED', '1') == '1'

# Paths exempt from rate limiting. Health probes from the load balancer
# shouldn't count against any band.
RATE_LIMITER_SKIP_PATHS = ['/health/', '/metrics', '/api/health/']

# Auto-ban escalation. An IP that produces > BAN_THRESHOLD 429s within
# BAN_THRESHOLD_WINDOW seconds gets banned for BAN_DURATION seconds.
# Cheap rejection: a banned IP exits at a single cache GET before any
# band counter increments.
RATE_LIMITER_BAN_THRESHOLD        = int(os.environ.get('RATE_LIMITER_BAN_THRESHOLD', '5'))
RATE_LIMITER_BAN_THRESHOLD_WINDOW = int(os.environ.get('RATE_LIMITER_BAN_THRESHOLD_WINDOW', '60'))
RATE_LIMITER_BAN_DURATION         = int(os.environ.get('RATE_LIMITER_BAN_DURATION', '600'))

# Trusted-proxy IPs for X-Forwarded-For honouring. Without this guard,
# any client can spoof XFF and look like it's coming from any IP. Set
# to the load-balancer / reverse-proxy egress IPs (e.g. ['10.0.0.5']).
# EMPTY in dev so REMOTE_ADDR is used directly.
TRUSTED_PROXY_IPS = [
    ip.strip()
    for ip in (os.environ.get('TRUSTED_PROXY_IPS', '') or '').split(',')
    if ip.strip()
]

# ── DB statement_timeout (middleware/db_timeout.py) ──────────
# The DSN-level default is 30s (DATABASES.default.OPTIONS.options).
# Per-path overrides let hot read endpoints fail FASTER (so one bad
# query doesn't tie up a pooled connection for 30s), and let admin
# reports legitimately run LONGER.
#
# Lookup is longest-prefix match. Unmatched paths inherit
# DB_STATEMENT_TIMEOUT_DEFAULT_MS.
DB_STATEMENT_TIMEOUT_DEFAULT_MS = int(
    os.environ.get('DB_STATEMENT_TIMEOUT_DEFAULT_MS', '30000')
)
DB_STATEMENT_TIMEOUT_BY_PATH = {
    # Read-heavy public endpoints: fail fast.
    '/api/v1/search/':       2000,
    '/api/v1/autocomplete':  1500,
    '/api/v1/products/':     5000,
    '/api/v1/categories/':   3000,
    '/api/v1/store':         5000,
    # Admin reports + bulk operations: legitimately slow.
    '/api/v1/admin/reports/':       300_000,  # 5 minutes
    '/api/v1/admin/exports/':       300_000,
    '/api/v1/admin/data-rights/':   180_000,  # 3 minutes (GDPR export)
    '/api/v1/admin/bulk-ops/':      180_000,
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,

    'filters': {
        'request_id': {
            '()': 'middleware.logging_middleware.StructuredLogFilter',
        },
    },

    'formatters': {
        'json': {
            '()': 'middleware.json_formatter.MichaJSONFormatter',
        },
        'text': {
            'format': '[%(asctime)s] %(levelname)s [%(request_id)s] %(name)s: %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
    },

    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': LOG_FORMAT,
            'filters': ['request_id'],
        },
        'error_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'errors.log',
            'maxBytes': 10 * 1024 * 1024,  # 10MB
            'backupCount': 5,
            'formatter': 'json',
            'filters': ['request_id'],
            'level': 'ERROR',
        },

        # Papertrail — structured syslog (add PAPERTRAIL_HOST + PORT to .env)
        'papertrail': {
            'class': 'logging.handlers.SysLogHandler',
            'formatter': 'json',
            'filters': ['request_id'],
            'address': (
                os.environ.get('PAPERTRAIL_HOST', 'logs.papertrailapp.com'),
                int(os.environ.get('PAPERTRAIL_PORT', 514)),
            ),
        },
        'security_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': BASE_DIR / 'logs' / 'security.log',
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 10,
            'formatter': 'json',
            'filters': ['request_id'],
            'level': 'INFO',
        },
    },

    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },

    'loggers': {
        # MICHA application logs
        'micha': {
            'handlers': ['console', 'error_file'] + (['papertrail'] if os.environ.get('PAPERTRAIL_HOST') else []),
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        # Request logs
        'micha.requests': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        # Security events (login, auth failures, suspicious activity)
        'micha.security': {
            'handlers': ['console', 'security_file'],
            'level': 'INFO',
            'propagate': False,
        },
        # Celery task logs
        'celery': {
            'handlers': ['console', 'error_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'celery.task': {
            'handlers': ['console', 'error_file'],
            'level': 'INFO',
            'propagate': False,
        },
        # Django internals — only warnings+
        'django': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['console', 'security_file'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console', 'error_file'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}

# Prohibited keywords for product listings (T&C compliance)
PROHIBITED_KEYWORDS = [
    'arma', 'pistola', 'revólver', 'rifle', 'explosivo', 'bomba',
    'droga', 'cocaína', 'heroína', 'cannabis', 'marijuana',
    'falsificado', 'pirata', 'ilegal', 'contraband',
    'pornografia', 'escort', 'prostituição',
]

# ── APPYPAY / Multicaixa Express ────────────────────────────────────
APPYPAY_API_KEY = os.environ.get('APPYPAY_API_KEY', '')
APPYPAY_SECRET = os.environ.get('APPYPAY_SECRET', '')
APPYPAY_MERCHANT_ID = os.environ.get('APPYPAY_MERCHANT_ID', '')
APPYPAY_BASE_URL = os.environ.get('APPYPAY_BASE_URL', 'https://api.appypay.co.ao/v1')
APPYPAY_WEBHOOK_URL = os.environ.get('APPYPAY_WEBHOOK_URL', '')

CSRF_COOKIE_HTTPONLY = True

# ── Security Headers ─────────────────────────────────────────────
SECURE_SSL_REDIRECT = os.environ.get('FORCE_HTTPS', 'false').lower() == 'true'
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'
PERMISSIONS_POLICY = {
    'geolocation': [],
    'camera': [],
    'microphone': [],
}


# ── Password Hashing — Argon2 (winner of Password Hashing Competition) ──
# Argon2id is resistant to GPU attacks, side-channel attacks, and time-memory tradeoffs
# Falls back to PBKDF2 for existing passwords (auto-upgraded on next login)
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
]

# ── Cache — Redis (shared across all workers) ────────────────────
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': os.environ.get('REDIS_URL', 'redis://localhost:6379/0'),
        'KEY_PREFIX': 'micha',
        'TIMEOUT': 300,
    }
}


# ── Boot-time security validation ─────────────────────────────────
# Runs at import time so a misconfigured production deploy fails BEFORE
# accepting traffic, rather than booting with insecure defaults.
#
# Skipped when DEBUG=True (dev) or when running under pytest / management
# commands where bypassing the check is intentional.

def _running_under_test_or_mgmt() -> bool:
    """True when the current invocation is a test runner or a one-shot
    management command (migrate, makemigrations, shell, etc.). These
    legitimately may run without prod-grade secrets."""
    import sys
    if 'pytest' in sys.modules or 'PYTEST_CURRENT_TEST' in os.environ:
        return True
    argv0 = (sys.argv[0] if sys.argv else '') or ''
    if argv0.endswith('manage.py') or argv0.endswith('manage'):
        # If a management command is being run, the second arg is the
        # subcommand. `runserver` and `daphne` are NOT management
        # commands we want to skip — those serve real traffic.
        cmd = sys.argv[1] if len(sys.argv) > 1 else ''
        if cmd and cmd not in ('runserver', 'daphne', 'gunicorn'):
            return True
    return False


if not DEBUG and not _running_under_test_or_mgmt():
    from django.core.exceptions import ImproperlyConfigured

    _problems = []

    if SECRET_KEY == _DEV_SECRET_KEY or not SECRET_KEY:
        _problems.append(
            'SECRET_KEY: refusing to boot with the dev default. '
            'Generate with: python -c "import secrets; print(secrets.token_urlsafe(60))" '
            'and set SECRET_KEY env var.'
        )

    if len(SECRET_KEY) < 40:
        _problems.append(
            f'SECRET_KEY: too short ({len(SECRET_KEY)} chars). '
            'Use at least 40 chars of secure random data.'
        )

    if not FIELD_ENCRYPTION_KEY:
        _problems.append(
            'FIELD_ENCRYPTION_KEY: not set. EncryptedCharField columns '
            '(bank accounts, 2FA secrets, IDs) cannot be encrypted.'
        )

    # If any third-party login is used, its client ID must be set. Empty
    # client_id is the Google-OAuth-accepts-any-audience bug.
    _google_login_attempted = bool(os.environ.get('GOOGLE_LOGIN_ENABLED', '0') == '1')
    if _google_login_attempted and not GOOGLE_CLIENT_ID:
        _problems.append(
            'GOOGLE_LOGIN_ENABLED=1 but GOOGLE_CLIENT_ID is empty. '
            'verify_oauth2_token with empty audience accepts tokens from '
            'ANY Google project — disabling auth entirely. Set GOOGLE_CLIENT_ID '
            'or unset GOOGLE_LOGIN_ENABLED.'
        )

    if _problems:
        raise ImproperlyConfigured(
            'MICHA refuses to boot due to insecure configuration:\n  - '
            + '\n  - '.join(_problems)
        )
