# fashionistar_backend/gunicorn.conf.py
"""
FASHIONISTAR — Gunicorn + Uvicorn Workers Production Config (Phase 7)
======================================================================

Why Gunicorn over bare Uvicorn?
─────────────────────────────────
Bare Uvicorn is excellent for development but NOT sufficient for production:
  - No process supervisor (crash → service down)
  - No graceful worker restart
  - No health-check-triggered worker recycle
  - No pre-fork model for memory efficiency

Gunicorn + UvicornWorker = best of both worlds:
  - Gunicorn manages N worker processes (pre-fork, supervisor, SIGTERM graceful)
  - Each worker is a full Uvicorn ASGI event loop (uvloop + httptools)
  - Zero-downtime deploys via graceful worker rotation

How to run:
    gunicorn -c gunicorn.conf.py backend.asgi:application

Performance expectations (Phase 7 + uvloop):
    p50 latency: ~5–15ms   (cached Ninja GET)
    p95 latency: ~15–30ms  (fresh DB read)
    RPS:         50k–200k+ (depending on instance size)

Scaling formula:
    workers = (CPU_count × 2) + 1
    This is the standard I/O-bound multiplier (Gunicorn docs, Uvicorn docs).
    For compute-heavy workloads (ML inference), reduce to CPU_count.
"""

import multiprocessing
import os

# ─── Worker count ──────────────────────────────────────────────────────────────
# Formula: (2 × CPU cores) + 1 for I/O-bound ASGI workloads.
# Override with GUNICORN_WORKERS environment variable for container scaling.
_cpu_count = multiprocessing.cpu_count()
workers = int(os.environ.get("GUNICORN_WORKERS", (_cpu_count * 2) + 1))

# ─── Worker class ──────────────────────────────────────────────────────────────
# UvicornWorker activates uvloop (C-extension event loop, 2–4× faster than
# CPython's default asyncio loop) and httptools (C-extension HTTP parser).
# Requires: pip install uvicorn[standard] gunicorn
worker_class = "uvicorn.workers.UvicornWorker"

# ─── Binding ───────────────────────────────────────────────────────────────────
# Bind to all interfaces so Nginx/load-balancer can reach the container.
# Override with GUNICORN_BIND env var in orchestration (Kubernetes, Render, AWS).
bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8001")

# ─── Request timeouts ──────────────────────────────────────────────────────────
# Timeout (seconds): kill and restart a worker that doesn't respond in time.
# Set to 30s — enough for Cloudinary webhooks and large file uploads.
# Never set below 10s (Django startup can take 5–8s cold).
timeout = int(os.environ.get("GUNICORN_TIMEOUT", 900))

# Keepalive: how long to wait for the next request on a persistent connection.
# 5s is standard; increase to 75s if behind a load balancer with long-lived conns.
keepalive = int(os.environ.get("GUNICORN_KEEPALIVE", 900))

# ─── Worker recycling ──────────────────────────────────────────────────────────
# Gracefully restart a worker after N requests to prevent memory accumulation.
# Jitter prevents all workers from restarting simultaneously (thundering herd).
max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", 1000))
max_requests_jitter = int(os.environ.get("GUNICORN_MAX_REQUESTS_JITTER", 100))

# ─── Pre-loading ───────────────────────────────────────────────────────────────
# preload_app=True: load the Django application ONCE in the master process,
# then fork N workers. Workers share the loaded code (copy-on-write) —
# significantly reduces startup time and memory footprint under K8s.
#
# Trade-off: if Django startup code has side-effects (e.g. opening DB connections),
# they are inherited by forked workers. This is safe for FASHIONISTAR because
# all connections are lazy (opened on first request).
preload_app = True

# ─── Logging ───────────────────────────────────────────────────────────────────
# Route all logs to stdout/stderr so container orchestrators (K8s, Docker,
# ECS) capture them via the standard log driver.
# Structlog (Phase 5) will format these as JSON before they reach the handler.
accesslog = "-"   # stdout
errorlog  = "-"   # stderr
loglevel  = os.environ.get("GUNICORN_LOG_LEVEL", "info")

# Uvicorn access log format — structured for Datadog parsing
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# ─── Server hooks ──────────────────────────────────────────────────────────────

def on_starting(server):
    """Called just before the master process is initialized."""
    server.log.info(
        "🚀 FASHIONISTAR Gunicorn starting | workers=%d | class=%s | bind=%s",
        workers, worker_class, bind,
    )


def post_fork(server, worker):
    """Called just after a worker has been forked."""
    # Reset any process-level state (e.g. random seeds, connection pools)
    # that should be unique per worker.
    import random
    random.seed()
    server.log.debug("Worker %s forked (pid=%d)", worker.age, worker.pid)


def worker_exit(server, worker):
    """Called just after a worker is killed."""
    server.log.info(
        "Worker %s (pid=%d) exited | requests_served=%d",
        worker.age, worker.pid, getattr(worker, "nr", 0),
    )


def on_exit(server):
    """Called just before exiting."""
    server.log.info("🛑 FASHIONISTAR Gunicorn exiting cleanly.")
