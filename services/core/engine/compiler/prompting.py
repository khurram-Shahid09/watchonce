"""What the Understand stage sees: compact candidates and a capped set of key frames
(docs/06-ai-pipeline.md steps 2-3)."""

from typing import Any

_ELEMENT_KEYS = ("tag", "role", "name", "label", "text", "nearby_text")
_CANDIDATE_KEYS = (
    "id", "action", "url", "value", "value_masked", "option_label", "key", "navigates_to", "notes",
)  # fmt: skip


def compact(candidate: dict[str, Any]) -> dict[str, Any]:
    """Drop locators and fingerprints (deterministic code handles those) and empty fields."""
    out = {k: candidate[k] for k in _CANDIDATE_KEYS if candidate.get(k) not in (None, "", [])}
    element = candidate.get("element") or {}
    slim = {k: element[k] for k in _ELEMENT_KEYS if element.get(k) not in (None, "", [])}
    if slim:
        out["element"] = slim
    if out.get("value_masked") is False:
        del out["value_masked"]
    return out


def pick_frames(
    candidates: list[dict[str, Any]], frame_names: list[str], limit: int
) -> list[tuple[str, str]]:
    """(label, frame name) pairs: one screenshot per candidate that has one, evenly thinned
    to ``limit``, plus the last frame of the recording labelled "final" (it usually shows
    the result, e.g. the new invoice number)."""
    seen: set[str] = set()
    per_step: list[tuple[str, str]] = []
    for c in candidates:
        ref = c.get("frame_ref")
        if ref and ref not in seen:
            seen.add(ref)
            per_step.append((c["id"], ref))

    final = sorted(frame_names)[-1] if frame_names else None
    if final in seen:
        final = None
    budget = limit - (1 if final else 0)
    if len(per_step) > budget > 0:
        step = len(per_step) / budget
        per_step = [per_step[int(i * step)] for i in range(budget)]
    return per_step + ([("final", final)] if final else [])
