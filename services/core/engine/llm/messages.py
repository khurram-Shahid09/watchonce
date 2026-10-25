"""Provider-neutral user messages: an ordered list of text and image parts. Each provider
maps parts onto its own content blocks; the wording is shared."""

import json
from typing import Any

from .types import Image, RepairRequest, SopRequest, UnderstandRequest

Part = str | Image


def understand_parts(req: UnderstandRequest) -> list[Part]:
    parts: list[Part] = [
        "Task description, written by the person who recorded it:\n"
        f"<description>\n{req.description}\n</description>",
        "Recorded candidate steps:\n```json\n"
        + json.dumps(req.candidates, ensure_ascii=False, indent=1)
        + "\n```",
    ]
    if req.images:
        parts.append(
            "Screenshots follow. Each is labelled with the candidate it was taken just "
            'before; "final" is the last page of the recording.'
        )
        for image in req.images:
            parts.append(f"[{image.label}]")
            parts.append(image)
    if req.feedback:
        parts.append(
            "Your previous answer could not be used. Fix these problems and answer again:\n"
            + "\n".join(f"- {problem}" for problem in req.feedback)
        )
    return parts


def _spec_for_prompt(spec: dict[str, Any]) -> dict[str, Any]:
    """The spec without locator internals, which only cost tokens here."""
    slim = dict(spec)
    slim["steps"] = []
    for step in spec.get("steps", []):
        step = dict(step)
        if "target" in step:
            fp = step["target"].get("fingerprint") or {}
            step["target"] = {
                k: fp.get(k) for k in ("role", "accessible_name", "text") if fp.get(k)
            }
        slim["steps"].append(step)
    slim.pop("source", None)
    return slim


def sop_parts(req: SopRequest) -> list[Part]:
    parts: list[Part] = [
        "Workflow specification:\n```json\n"
        + json.dumps(_spec_for_prompt(req.spec), ensure_ascii=False, indent=1)
        + "\n```"
    ]
    if req.images:
        parts.append("Screenshots, labelled with their screenshot_ref:")
        for image in req.images:
            parts.append(f"[{image.label}]")
            parts.append(image)
    return parts


def repair_parts(req: RepairRequest) -> list[Part]:
    context = {
        "intent": req.intent,
        "action": req.action,
        "previous_step": req.previous_intent,
        "next_step": req.next_intent,
        "page_url": req.page_url,
        "recorded_element": req.fingerprint,
    }
    parts: list[Part] = [
        "Step to repair:\n```json\n" + json.dumps(context, ensure_ascii=False, indent=1) + "\n```",
        "Candidate elements on the current page, most similar first:\n```json\n"
        + json.dumps(req.candidates, ensure_ascii=False, indent=1)
        + "\n```",
    ]
    for image in req.images:
        parts.append(f"[{image.label}]")
        parts.append(image)
    return parts
