from config.settings import *
import os

DEBUG = True
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Test database.
#
# Two modes:
#   CI / production-like:   keep Postgres (the import * above provides
#       config.settings.DATABASES which is Postgres in prod). Set
#       TEST_DB_POSTGRES=1 in CI to use this path.
#
#   Local dev (default):    SQLite in-memory. Runs everywhere without
#       needing a local Postgres + role setup. Trade-off: SQLite does
#       not support select_for_update + skip_locked the same way
#       Postgres does, so concurrency tests effectively serialise.
#       That's a TEST limitation, not a code-correctness issue —
#       the production lock semantics still apply.
if os.environ.get('TEST_DB_POSTGRES', '0') != '1':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:',
        }
    }
else:
    # Inherits Postgres DATABASES['default'] from config.settings. We
    # only override the TEST sub-config to name the test DB explicitly.
    #
    # IMPORTANT: do NOT include ``DEPENDENCIES: ['default']`` here.
    # That tells Django the 'default' database depends on itself —
    # which raises ``ImproperlyConfigured: Circular dependency:
    # databases ['default'] depend on each other, but are aliases``
    # before any test runs. DEPENDENCIES is only for setups with
    # MULTIPLE databases where one needs to be created before another;
    # we have only one DB.
    DATABASES['default']['TEST'] = {
        'NAME': 'test_micha',
    }

# Skip migration_guard checks during tests; the guard is for production
# migration safety, not test runtime.
MIGRATION_UNSAFE_ALLOWED = True

# Force rate limiter off in tests (compose interferes with throttle tests).
RATE_LIMITER_ENABLED = False

# Speed up password hashing in tests
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

# Disable celery in tests
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Disable rate limiting in tests
RATELIMIT_ENABLE = False
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    'DEFAULT_THROTTLE_CLASSES': [],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '10000/day',
        'user': '10000/day',
        'login': '10000/day',
        'register': '10000/day',
        'payment': '10000/day',
        'checkout': '10000/day',
        'burst': '10000/day',
        'sustained': '10000/day',
    },
}

FIELD_ENCRYPTION_KEY = 'XGG4Y1gf3jGtfnchHSORV2lIyeh0Sj6-j8Hn4ECHVJo='

# Disable custom logging in tests
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'root': {'handlers': ['console'], 'level': 'WARNING'},
}
