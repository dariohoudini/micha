"""
WSGI entrypoint for production.
Run with gunicorn — never use manage.py runserver in production.

Start command:
    gunicorn config.wsgi:application \
        --bind 0.0.0.0:8000 \
        --workers 4 \
        --worker-class gthread \
        --threads 4 \
        --timeout 120 \
        --graceful-timeout 30 \
        --max-requests 1000 \
        --max-requests-jitter 100 \
        --access-logfile - \
        --error-logfile - \
        --log-level info

Workers formula: (2 × CPU cores) + 1
On a 2-core server: 5 workers
On a 4-core server: 9 workers
"""
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
application = get_wsgi_application()
