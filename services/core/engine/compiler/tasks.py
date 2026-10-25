"""Celery entry point for compiling a recording (queue ``compile``).

Day 5 runs the deterministic stages: validate ``events.json``, normalize, build locators and
store ``candidates.json``. The recording then waits in ``uploaded`` with ``candidate_count``
set; the Understand stage (Claude) picks it up from there on Day 6.
"""

import json
import logging

from celery import shared_task
from pydantic import ValidationError

from common.storage import get_storage

from .normalize import normalize
from .recording import Recording as RecordingFile

log = logging.getLogger(__name__)


@shared_task(name="engine.compiler.compile_recording", acks_late=True)
def compile_recording(recording_id: str) -> None:
    from recordings.models import Recording

    recording = Recording.objects.filter(pk=recording_id).first()
    if recording is None or recording.status != Recording.Status.UPLOADED:
        log.info("compile skipped: %s not waiting to compile", recording_id)
        return

    storage = get_storage()
    try:
        raw = json.loads(storage.get_bytes(recording.key("events.json")))
        parsed = RecordingFile.model_validate(raw)
    except (ValueError, ValidationError) as exc:
        # ValidationError subclasses ValueError; json errors too. Never echo file contents.
        recording.status = Recording.Status.FAILED
        recording.error = f"The uploaded recording file is invalid ({type(exc).__name__})."
        recording.save(update_fields=["status", "error", "updated_at"])
        log.warning("compile failed: %s has an invalid events.json", recording_id)
        return

    result = normalize(parsed)
    storage.put_bytes(
        recording.key("candidates.json"),
        json.dumps(result, ensure_ascii=False).encode(),
        "application/json",
    )
    recording.candidate_count = result["stats"]["candidates"]
    recording.save(update_fields=["candidate_count", "updated_at"])
    log.info(
        "normalized %s: %d events -> %d candidates",
        recording_id,
        result["stats"]["raw_events"],
        recording.candidate_count,
    )
