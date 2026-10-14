"""Task definitions executed by the Celery workers.

Each module here holds the tasks for one unit of work; they are wired in via
``TASK_MODULES`` in :mod:`workers.celery_app`.
"""