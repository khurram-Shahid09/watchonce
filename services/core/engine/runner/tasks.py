"""Celery entry point for runs (queue ``run``).

Never retried or redelivered: a run that died half way may already have submitted
something, so it ends as failed and a person decides whether to run it again.
"""

import logging

from celery import shared_task
from django import db
from django.utils import timezone

log = logging.getLogger(__name__)


@shared_task(name="engine.runner.execute_run", acks_late=False)
def execute_run(run_id: str) -> None:
    from runs.models import Run

    from .browser import get_browser
    from .executor import Executor

    claimed = Run.objects.filter(pk=run_id, status=Run.Status.QUEUED).update(
        status=Run.Status.RUNNING, started_at=timezone.now()
    )
    if not claimed:
        log.info("run %s skipped: not queued", run_id)
        return
    run = Run.objects.select_related("org", "version", "workflow").get(pk=run_id)
    try:
        Executor(run, get_browser()).execute()
    finally:
        # Playwright's loop gives Django a separate connection context; don't leak it.
        db.connections.close_all()
