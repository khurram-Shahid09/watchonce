"""Celery entry point for compiling a recording (queue ``compile``).

uploaded → compiling → compiled (workflow v1 saved) | failed (``error`` says why).
Transient AI errors (rate limits, outages) retry with exponential backoff, up to 3 times.
"""

import logging

from celery import shared_task
from django.db.models import Q

from engine.llm import LLMError

from .pipeline import CompileError
from .pipeline import compile_recording as run_pipeline

log = logging.getLogger(__name__)
MAX_RETRIES = 3


@shared_task(
    name="engine.compiler.compile_recording", bind=True, acks_late=True, max_retries=MAX_RETRIES
)
def compile_recording(self, recording_id: str) -> None:
    from audit.service import record
    from recordings.models import Recording

    # Claim it. Only one task compiles a recording: a fresh one claims "uploaded", and its
    # own retries (same task id) continue a "compiling" claim. A stray duplicate does nothing.
    task_id = self.request.id or ""
    claimed = (
        Recording.objects.filter(pk=recording_id)
        .filter(
            Q(status=Recording.Status.UPLOADED)
            | Q(status=Recording.Status.COMPILING, compile_task_id=task_id)
        )
        .update(status=Recording.Status.COMPILING, error="", error_code="", compile_task_id=task_id)
    )
    if not claimed:
        log.info("compile skipped: %s isn't waiting to compile", recording_id)
        return
    recording = Recording.objects.select_related("org", "user").get(pk=recording_id)

    def fail(code: str, message: str) -> None:
        recording.status = Recording.Status.FAILED
        recording.error, recording.error_code = message[:2000], code
        recording.save(update_fields=["status", "error", "error_code", "updated_at"])
        record(
            "recording.compile_failed",
            org=recording.org,
            entity=recording,
            actor="system:compiler",
            metadata={"code": code},
        )

    try:
        workflow = run_pipeline(recording)
    except CompileError as exc:
        log.warning("compile %s failed: %s %s", recording_id, exc.code, exc.details[:5])
        detail = f" ({'; '.join(exc.details[:3])})" if exc.details else ""
        fail(exc.code, exc.message + detail)
        return
    except LLMError as exc:
        if exc.retryable and self.request.retries < MAX_RETRIES:
            log.info("compile %s: %s, retrying", recording_id, exc.code)
            raise self.retry(exc=exc, countdown=15 * 2**self.request.retries) from exc
        if exc.retryable:  # retries used up
            fail(
                exc.code,
                f"{exc.message} Tried {self.request.retries + 1} times; use Compile again in a few minutes.",
            )
        else:
            fail(exc.code, exc.message)
        return
    except Exception:
        log.exception("compile %s crashed", recording_id)
        fail("internal_error", "Something went wrong while compiling. Try again.")
        raise

    recording.status = Recording.Status.COMPILED
    recording.save(update_fields=["status", "updated_at"])
    record(
        "recording.compiled",
        org=recording.org,
        entity=recording,
        actor="system:compiler",
        metadata={"workflow_id": workflow.id},
    )
    log.info("compiled %s into %s", recording_id, workflow.id)
