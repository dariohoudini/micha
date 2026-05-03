from config.settings import *

DEBUG = True
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

DATABASES['default']['TEST'] = {'NAME': 'test_micha', 'MIRROR': None, 'CHARSET': None, 'COLLATION': None, 'DEPENDENCIES': ['default'], 'CREATE_DB': True}

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
