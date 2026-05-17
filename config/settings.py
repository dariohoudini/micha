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
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-dev-only-change-in-production')
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
    'apps.telemetry.middleware.MetricsMiddleware',
    # QueryBudgetMiddleware OUTSIDE QueryAuditMiddleware so its response-
    # phase code runs AFTER query_audit sets request._db_queries.
    'middleware.query_budget.QueryBudgetMiddleware',
    'apps.telemetry.query_audit.QueryAuditMiddleware',
    'middleware.security_hardening.SecurityHardeningMiddleware',
    'middleware.security_hardening.FileUploadSecurityMiddleware',
    'middleware.terms_version.TermsVersionMiddleware',
    'middleware.sanitise.SanitiseInputMiddleware',
    'apps.verification_gate.middleware.SellerVerificationMiddleware',
    'apps.dev_keys.middleware.APIKeyUsageMiddleware',
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

# FIX: Read replica routing — analytics + reports hit replica, writes hit primary
# Uncomment when you have a read replica
# DATABASE_ROUTERS = ['config.db_router.ReadReplicaRouter']

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
    'DEFAULT_THROTTLE_RATES': {
        'anon': '10000/hour',
        'user': '10000/hour',
        'login': '10000/hour',
        'register': '10000/hour',
        'otp': '5/hour',
        'otp_verify': '5/hour',
        'payment': '20/hour',
        'login': '10/minute',
        'register': '5/minute',
        'otp': '5/minute',
        'search': '60/minute',
        'upload': '20/hour',
        'anon_burst': '30/minute',
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
CELERY_TASK_QUEUES = {
    'high': {'exchange': 'high', 'routing_key': 'high'},
    'default': {
        'TEST': {
            'NAME': 'test_micha',
        },'exchange': 'default', 'routing_key': 'default'},
    'low': {'exchange': 'low', 'routing_key': 'low'},
    'dead_letter': {'exchange': 'dead_letter', 'routing_key': 'dead_letter'},
}
CELERY_TASK_DEFAULT_QUEUE = 'default'
CELERY_TASK_ROUTES = {
    'orders.*': {'queue': 'high'},
    'notifications.*': {'queue': 'high'},
    'payments.*': {'queue': 'high'},
    'recommendations.weekly_digest': {'queue': 'low'},
    'recommendations.recalculate_similarity': {'queue': 'low'},
    'collections.record_price_history': {'queue': 'low'},
    
}
CELERY_BEAT_SCHEDULE = {

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
        'task': 'cart.send_abandonment_nudge',
        'schedule': 1800,  # every 30 min
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
if SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.redis import RedisIntegration
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            integrations=[DjangoIntegration(), CeleryIntegration(), RedisIntegration()],
            traces_sample_rate=0.1,
            send_default_pii=False,
        )
    except ImportError:
        pass

# ── Logging ───────────────────────────────────────────────────────────────────
# ── Logging ─────────────────────────────────────────────────────
LOG_FORMAT = os.environ.get('LOG_FORMAT', 'json')  # 'json' or 'text'

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
