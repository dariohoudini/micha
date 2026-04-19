"""
Gunicorn configuration file.
Place in project root. Load with: gunicorn -c config/gunicorn.conf.py config.wsgi:application
"""
import multiprocessing
import os

# ── Workers ───────────────────────────────────────────────────────────────────
# Formula: (2 × CPU cores) + 1
workers = int(os.environ.get('GUNICORN_WORKERS', multiprocessing.cpu_count() * 2 + 1))
worker_class = 'gthread'        # threads per worker — better for I/O bound Django
threads = int(os.environ.get('GUNICORN_THREADS', 4))
worker_connections = 1000

# ── Timeouts ──────────────────────────────────────────────────────────────────
timeout = 120           # kill worker if request takes > 120 seconds
graceful_timeout = 30   # give workers 30s to finish current request on shutdown
keepalive = 5           # keep connection alive for 5 seconds

# ── Binding ───────────────────────────────────────────────────────────────────
bind = os.environ.get('GUNICORN_BIND', '0.0.0.0:8000')

# ── Worker recycling — prevents memory leaks ──────────────────────────────────
max_requests = 1000             # restart worker after 1000 requests
max_requests_jitter = 100       # randomise restart to prevent all workers restarting at once

# ── Logging ───────────────────────────────────────────────────────────────────
accesslog = '-'         # stdout
errorlog = '-'          # stderr
loglevel = os.environ.get('GUNICORN_LOG_LEVEL', 'info')
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# ── Process naming ────────────────────────────────────────────────────────────
proc_name = 'micha-api'

# ── Security ─────────────────────────────────────────────────────────────────
limit_request_line = 8190
limit_request_fields = 100
limit_request_field_size = 8190

# ── Hooks ─────────────────────────────────────────────────────────────────────
def on_starting(server):
    server.log.info("MICHA API starting up")

def post_fork(server, worker):
    server.log.info(f"Worker {worker.pid} started")

def worker_exit(server, worker):
    server.log.info(f"Worker {worker.pid} exited")

def on_exit(server):
    server.log.info("MICHA API shutting down")
