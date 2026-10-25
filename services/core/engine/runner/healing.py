"""Self-healing rungs L2 (fingerprint match) and the checks that guard L3 (AI repair)
(docs/08-runner-and-self-healing.md "Self-healing ladder").

Everything here is plain Python over element descriptors, so it is unit-tested without a
browser. The browser side (listing candidates) is engine/runner/static/page-agent.js,
built from the recorder's own descriptor code.
"""

import math
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from engine.compiler.recording import Element

# Weights from docs/08 ("tuned with the eval suite" on Day 13).
WEIGHTS = {
    "role": 0.20,
    "name": 0.25,
    "text": 0.15,
    "attributes": 0.15,
    "nearby": 0.15,
    "position": 0.10,
}
L2_ACCEPT = 0.75  # top score needed to heal without the AI
L2_MARGIN = 0.10  # ...and this far ahead of the runner-up (an unambiguous winner)
L2_SELF_APPROVE = 0.90  # below this, the healed version needs a person's approval
L3_FLOOR = 0.40  # an AI pick scoring below this is "a completely different element"
L3_MIN_CONFIDENCE = 0.60
STABLE_ATTRS = ("name", "type", "placeholder", "aria-label", "title", "href", "for")

# Which roles can take which action (L3 verification).
ACTION_ROLES: dict[str, set[str] | None] = {
    "fill": {"textbox", "searchbox", "combobox", "spinbutton"},
    "select": {"combobox", "listbox", "button"},
    "check": {"checkbox", "radio", "switch", "menuitemcheckbox"},
    "uncheck": {"checkbox", "radio", "switch", "menuitemcheckbox"},
    "click": None,  # anything clickable
    "press": None,
    "extract": None,
}

_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str | None) -> set[str]:
    return set(_WORD.findall((text or "").lower()))


def text_similarity(a: str | None, b: str | None) -> float:
    """Max of normalized edit similarity and token overlap. Both empty (e.g. two input
    fields, which have no text) is a match; only one empty is not."""
    a, b = (a or "").strip().lower(), (b or "").strip().lower()
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ta, tb = _tokens(a), _tokens(b)
    overlap = len(ta & tb) / len(ta | tb) if ta | tb else 0.0
    return max(SequenceMatcher(None, a, b).ratio(), overlap)


def _overlap(a: set[str], b: set[str]) -> float:
    """Overlap relative to the smaller set: a redesign that *removes* attributes or nearby
    words (test ids stripped, a heading dropped) shouldn't count against a match twice."""
    return len(a & b) / min(len(a), len(b)) if a and b else 0.0


def _stable_attrs(attrs: dict[str, Any]) -> set[str]:
    pairs = set()
    for key, value in attrs.items():
        if value and (key in STABLE_ATTRS or key.startswith("data-") or key in ("id", "class")):
            pairs.add(f"{key}={value}")
    return pairs


def score(fingerprint: dict[str, Any], candidate: Element) -> float:
    """How likely ``candidate`` is the recorded element (0..1)."""
    parts: dict[str, float] = {}
    parts["role"] = (
        1.0 if fingerprint.get("role") and fingerprint.get("role") == candidate.role else 0.0
    )
    parts["name"] = text_similarity(fingerprint.get("accessible_name"), candidate.accessible_name)
    parts["text"] = text_similarity(fingerprint.get("text"), candidate.text)

    cand_attrs = {k: v for k, v in candidate.attrs.items() if v}
    if candidate.id:
        cand_attrs["id"] = candidate.id
    if candidate.classes:
        cand_attrs["class"] = " ".join(candidate.classes)
    fa, ca = _stable_attrs(fingerprint.get("attributes") or {}), _stable_attrs(cand_attrs)
    parts["attributes"] = _overlap(fa, ca)

    fn = _tokens(" ".join(fingerprint.get("nearby_text") or []))
    cn = _tokens(" ".join(candidate.nearby_text))
    parts["nearby"] = _overlap(fn, cn)

    box = fingerprint.get("bbox_norm")
    vw, vh = candidate.viewport
    if box and vw and vh:
        x, y, w, h = candidate.bbox
        cx, cy = (x + w / 2) / vw, (y + h / 2) / vh
        fx, fy = box[0] + box[2] / 2, box[1] + box[3] / 2
        parts["position"] = max(0.0, 1.0 - math.hypot(cx - fx, cy - fy) / math.sqrt(2))
    else:
        parts["position"] = 0.0
    return round(sum(WEIGHTS[k] * v for k, v in parts.items()), 4)


@dataclass
class Ranked:
    id: str
    element: Element
    score: float
    enabled: bool


def rank(fingerprint: dict[str, Any], candidates: list[dict[str, Any]]) -> list[Ranked]:
    ranked = []
    for c in candidates:
        try:
            element = Element.model_validate(c["descriptor"])
        except ValueError:
            continue
        ranked.append(
            Ranked(c["id"], element, score(fingerprint, element), bool(c.get("enabled", True)))
        )
    return sorted(ranked, key=lambda r: r.score, reverse=True)


def action_fits(action: str, element: Element) -> bool:
    roles = ACTION_ROLES.get(action)
    if roles is None:
        return True
    if action == "fill" and element.tag in ("input", "textarea"):
        return element.attrs.get("type") not in ("checkbox", "radio", "submit", "button", "file")
    if action == "select" and element.tag == "select":
        return True
    return element.role in roles


def l2_pick(action: str, ranked: list[Ranked]) -> Ranked | None:
    """An unambiguous, confident fingerprint winner that can take the step's action."""
    usable = [r for r in ranked if r.enabled and action_fits(action, r.element)]
    if not usable or usable[0].score < L2_ACCEPT:
        return None
    runner_up = usable[1].score if len(usable) > 1 else 0.0
    return usable[0] if usable[0].score - runner_up >= L2_MARGIN else None


def l3_verify(action: str, pick: Ranked, confidence: float) -> str | None:
    """Why an AI pick can't be used, or None if it passes every check (docs/08 L3)."""
    if not pick.enabled:
        return "the chosen element is disabled"
    if not action_fits(action, pick.element):
        return f"a {pick.element.role or pick.element.tag} can't take a {action}"
    if pick.score < L3_FLOOR:
        return f"it looks nothing like the recorded element (score {pick.score:.2f})"
    if confidence < L3_MIN_CONFIDENCE:
        return f"the AI wasn't confident enough ({confidence:.2f})"
    return None


def describe_change(fingerprint: dict[str, Any], element: Element) -> str:
    """A short human explanation for L2 heals (L3 heals use the AI's explanation)."""
    before = fingerprint.get("accessible_name") or fingerprint.get("text") or fingerprint.get("tag")
    after = element.accessible_name or element.text or element.tag
    if before and after and before != after:
        return f"“{before}” is now “{after}” (same kind of element, nearby text and position)."
    return "The element is the same but its id, classes or position changed."
