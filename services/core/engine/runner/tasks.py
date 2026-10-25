"""Celery entry point for runs (queue ``run``).

Never retried or redelivered: a run that died half way may already have submitted
something, so it ends as failed and a person decides whether to run it again.
"""

import logging

from celery import shared_task
from django import db
from django.db import models
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


@shared_task(name="engine.runner.execute_batch", acks_late=False)
def execute_batch(batch_id: str) -> None:
    """Run a batch's rows one after another. A failed row doesn't stop the batch."""
    from runs.models import Batch, Run

    from .browser import get_browser
    from .executor import Executor

    claimed = Batch.objects.filter(pk=batch_id, status=Batch.Status.QUEUED).update(
        status=Batch.Status.RUNNING
    )
    if not claimed:
        log.info("batch %s skipped: not queued", batch_id)
        return
    try:
        for run_id in (
            Batch.objects.get(pk=batch_id).runs.order_by("row_index").values_list("id", flat=True)
        ):
            if Batch.objects.filter(pk=batch_id, status=Batch.Status.CANCELLED).exists():
                break
            started = Run.objects.filter(pk=run_id, status=Run.Status.QUEUED).update(
                status=Run.Status.RUNNING, started_at=timezone.now()
            )
            if not started:
                continue
            run = Run.objects.select_related("org", "version", "workflow").get(pk=run_id)
            Executor(run, get_browser()).execute()
            run.refresh_from_db(fields=["status"])
            field = "succeeded" if run.status == Run.Status.SUCCEEDED else "failed"
            Batch.objects.filter(pk=batch_id).update(**{field: models.F(field) + 1})
    finally:
        Batch.objects.filter(pk=batch_id, status=Batch.Status.RUNNING).update(
            status=Batch.Status.FINISHED, finished_at=timezone.now()
        )
        db.connections.close_all()
