"""Run a worker with::celery -A workers.celery_app.celery_app worker --loglevel=info"""

from __future__ import annotations

import os

from celery import Celery
from dotenv import load_dotenv

load_dotenv()

#: Modules holding task definitions; imported by the worker at startup.
TASK_MODULES = ["workers.processes.ingestion"]

BROKER_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", BROKER_URL)

celery_app = Celery(
    "clairvoyant",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=TASK_MODULES,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Report STARTED as well as SUCCESS/FAILURE so callers can tell queued from
    # actually running.
    task_track_started=True,
    # Survive a broker that is still booting alongside the app.
    broker_connection_retry_on_startup=True,
    # Redeliver a task if the worker dies mid-run rather than dropping it.
    task_acks_late=True,
    # One long ingestion task at a time per worker; prefetching would let a
    # worker hoard jobs it cannot start yet.
    worker_prefetch_multiplier=1,
)
