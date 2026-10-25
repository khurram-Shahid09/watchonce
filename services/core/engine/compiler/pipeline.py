"""Compile a recording into workflow v1 (docs/06-ai-pipeline.md, the whole flowchart).

normalize → key frames → Understand (AI) → check → assemble → validate → (retry once with
the problems) → SOP (AI, falls back to a plain SOP) → save workflow + version 1.
"""

import json
import logging
from typing import Any

from django.conf import settings
from django.db import transaction

from common.storage import get_storage
from engine.llm import LLMError, get_provider, load_prompt
from engine.llm.types import Image, SopRequest, UnderstandRequest
from engine.spec.validate import validate_spec

from .assemble import assemble, check
from .normalize import normalize
from .prompting import compact, pick_frames
from .recording import Recording as RecordingFile
from .sop import render_basic_sop

log = logging.getLogger(__name__)


class CompileError(Exception):
    def __init__(self, code: str, message: str, details: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or []


def load_candidates(recording) -> dict[str, Any]:
    """candidates.json, normalizing the raw upload first if that hasn't happened yet."""
    storage = get_storage()
    if recording.candidate_count is not None:
        return json.loads(storage.get_bytes(recording.key("candidates.json")))
    try:
        parsed = RecordingFile.model_validate(
            json.loads(storage.get_bytes(recording.key("events.json")))
        )
    except ValueError as exc:  # json and pydantic errors; never echo file contents
        raise CompileError(
            "invalid_recording", f"The uploaded recording file is invalid ({type(exc).__name__})."
        ) from exc
    result = normalize(parsed)
    storage.put_bytes(
        recording.key("candidates.json"),
        json.dumps(result, ensure_ascii=False).encode(),
        "application/json",
    )
    recording.candidate_count = result["stats"]["candidates"]
    recording.save(update_fields=["candidate_count", "updated_at"])
    return result


def _images(recording, pairs: list[tuple[str, str]]) -> list[Image]:
    storage = get_storage()
    images = []
    for label, name in pairs:
        if storage.size(recording.key(name)) is None:
            continue  # tolerated: frames are helpful, not required
        images.append(Image(label=label, data=storage.get_bytes(recording.key(name))))
    return images


def _log_call(recording, purpose: str, usage, prompt_version: str, error_code: str = "") -> None:
    from metering.service import record_call

    if usage is not None:
        record_call(
            org=recording.org,
            purpose=purpose,
            usage=usage,
            entity_id=recording.id,
            prompt_version=prompt_version,
            error_code=error_code,
        )


def understand_and_assemble(
    recording, doc: dict[str, Any]
) -> tuple[dict[str, Any], list[str], dict[str, Any]]:
    candidates = doc["candidates"]
    provider = get_provider("understand")
    _, prompt_version = load_prompt("understand", provider.name)
    frames = pick_frames(candidates, recording.frame_names, settings.COMPILE_MAX_FRAMES)
    request = UnderstandRequest(
        description=recording.description,
        candidates=[compact(c) for c in candidates],
        images=_images(recording, frames),
    )
    compiled_by = f"{provider.name}:{provider.model}"
    problems: list[str] = []
    for attempt in (1, 2):
        try:
            understanding, usage = provider.understand(request)
        except LLMError as exc:
            _log_call(recording, "understand", exc.usage, prompt_version, exc.code)
            raise
        _log_call(recording, "understand", usage, prompt_version)
        compiled_by = f"{usage.provider}:{usage.model}"
        problems = check(candidates, understanding)
        if not problems:
            spec, warnings = assemble(
                candidates, understanding, recording_id=recording.id, compiled_by=compiled_by
            )
            result = validate_spec(spec)
            problems = [f"{issue.path}: {issue.message}" for issue in result.errors]
            if not problems:
                warnings += [f"{w.path}: {w.message}" for w in result.warnings]
                warnings += [f"Recorder: {w}" for w in doc.get("warnings", [])]
                info = {
                    "understand": {
                        "by": compiled_by,
                        "prompt": prompt_version,
                        "attempts": attempt,
                    },
                    "frames_sent": len(request.images),
                    "candidates": len(candidates),
                }
                return spec, warnings, info
        log.info("compile %s attempt %d unusable: %s", recording.id, attempt, problems[:5])
        request.feedback = problems
    raise CompileError(
        "compile_invalid", "The AI couldn't produce a valid workflow for this recording.", problems
    )


def write_sop(recording, spec: dict[str, Any]) -> tuple[str, dict[str, Any], list[str]]:
    """AI SOP, or the plain rendering if the AI call fails (never blocks the compile)."""
    pairs = [
        (s["screenshot_ref"], s["screenshot_ref"]) for s in spec["steps"] if s.get("screenshot_ref")
    ]
    try:
        provider = get_provider("sop")
        _, prompt_version = load_prompt("sop", provider.name)
        images = _images(recording, pairs[: settings.COMPILE_MAX_FRAMES])
        try:
            result, usage = provider.write_sop(SopRequest(spec=spec, images=images))
        except LLMError as exc:
            _log_call(recording, "sop", exc.usage, prompt_version, exc.code)
            raise
        _log_call(recording, "sop", usage, prompt_version)
        return (
            result.markdown,
            {"by": f"{usage.provider}:{usage.model}", "prompt": prompt_version},
            [],
        )
    except LLMError as exc:
        log.warning("SOP for %s fell back to the plain version: %s", recording.id, exc.code)
        return (
            render_basic_sop(spec),
            {"by": "plain"},
            [f"SOP: the AI version failed ({exc.message}); showing the plain version."],
        )


def compile_recording(recording):
    """Returns the new Workflow. Raises CompileError or LLMError."""
    from metering.service import budget_left
    from workflows.models import Workflow
    from workflows.service import create_version

    existing = Workflow.objects.filter(recording=recording).first()
    if existing is not None:  # compiled already (e.g. a redelivered task): nothing to redo
        return existing

    doc = load_candidates(recording)
    if not doc["candidates"]:
        raise CompileError("empty_recording", "The recording has no steps.")
    if len(doc["candidates"]) > settings.COMPILE_MAX_CANDIDATES:
        raise CompileError(
            "recording_too_long",
            f"The recording has {len(doc['candidates'])} steps; the limit is "
            f"{settings.COMPILE_MAX_CANDIDATES}. Record a shorter task.",
        )
    if not budget_left(recording.org):
        raise CompileError("budget_exceeded", "This workspace reached its monthly AI budget.")

    spec, warnings, info = understand_and_assemble(recording, doc)
    sop, sop_info, sop_warnings = write_sop(recording, spec)
    info["sop"] = sop_info

    with transaction.atomic():
        workflow = Workflow.objects.create(
            org=recording.org,
            name=spec["name"],
            description=spec.get("description", ""),
            recording=recording,
            created_by=recording.user,
        )
        create_version(
            workflow,
            spec,
            created_by="compiler",
            sop_markdown=sop,
            warnings=warnings + sop_warnings,
            activate=True,
            compile_info=info,
            change_note="Compiled from the recording",
        )
    return workflow
