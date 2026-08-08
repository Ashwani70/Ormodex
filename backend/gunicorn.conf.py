"""Gunicorn config for the Hostinger VPS systemd deployment (see
deploy/erp-backend.service). Not used by Railway/Docker, which invokes
uvicorn directly (see Dockerfile's CMD) — this file is VPS-specific.

Workload here is I/O-bound (DB round-trips to the remote Supabase pooler,
not local CPU work), so workers = 2x cores + 1 is the standard Gunicorn
guidance and comfortably covers 500+ concurrent users given the app has no
long-lived connections (HTTP request/response only, no websockets as of
this writing) — each worker handles many overlapping requests via asyncio,
it isn't one worker per concurrent user.
"""
import multiprocessing
import os

bind = f"127.0.0.1:{os.getenv('PORT', '8001')}"

workers = int(os.getenv("WEB_CONCURRENCY", multiprocessing.cpu_count() * 2 + 1))
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000

# Recycle workers periodically to bound the impact of any slow memory leak.
max_requests = 2000
max_requests_jitter = 200

timeout = 60
graceful_timeout = 30
keepalive = 5

accesslog = "/var/www/erp/backend/logs/access.log"
errorlog = "/var/www/erp/backend/logs/error.log"
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")

preload_app = True
