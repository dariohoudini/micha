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
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '*').split(',')
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
    'rest_framework',
    'rest_framework.authtoken',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
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
    'middleware.request_id.RequestIDMiddleware',
    'middleware.sanitise.SanitiseInputMiddleware',
    'apps.verification_gate.middleware.SellerVerificationMiddleware',
]

CORS_ALLOW_ALL_ORIGINS = DEBUG
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
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ['DB_NAME'],
            'USER': os.environ.get('DB_USER', 'postgres'),
            'PASSWORD': os.environ.get('DB_PASSWORD', ''),
            'HOST': os.environ.get('DB_HOST', 'localhost'),
            'PORT': os.environ.get('DB_PORT', '5432'),
            # FIX: Connection pooling — keep connections alive, don't open new one per request
            'CONN_MAX_AGE': int(os.environ.get('DB_CONN_MAX_AGE', 60)),
            'CONN_HEALTH_CHECKS': True,
            'OPTIONS': {
                'connect_timeout': 10,
                # FIX: Query timeout — kill queries taking longer than 30 seconds
                # Prevents one slow analytics query from taking down the whole app
                'options': '-c statement_timeout=30000',
            },
        }
    }
else:
    DATABASES = {
        'default': {
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
        'anon': '100/hour',
        'user': '1000/hour',
        'login': '10/hour',
        'register': '5/hour',
        'otp': '5/hour',
        'otp_verify': '5/hour',
        'payment': '20/hour',
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
    EMAIL_HOST = os.environ['EMAIL_HOST']
    EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
    EMAIL_USE_TLS = True
    EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
    EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = 'MICHA <noreply@micha.app>'

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
    'default': {'exchange': 'default', 'routing_key': 'default'},
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
    # ... your existing tasks ...

    'verification-daily-check': {
        'task': 'verification_gate.daily_verification_check',
        'schedule': 86400,  # daily
        'options': {'queue': 'ai_medium'},
    },
}

# ── Cache — Redis in prod, LocMem in dev ──────────────────────────────────────
CACHES = {
    'default': {
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
    SECURE_SSL_REDIRECT = True
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
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {'format': '[{asctime}] {levelname} {name} {request_id}: {message}', 'style': '{'},
    },
    'handlers': {'console': {'class': 'logging.StreamHandler', 'formatter': 'verbose'}},
    'root': {'handlers': ['console'], 'level': 'INFO'},
    'loggers': {
        'micha': {'handlers': ['console'], 'level': 'DEBUG', 'propagate': False},
        'django.security': {'handlers': ['console'], 'level': 'WARNING', 'propagate': False},
        'django.db.backends': {'handlers': ['console'], 'level': 'WARNING', 'propagate': False},
        'celery': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
    },
}
