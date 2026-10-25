"""Locators and fingerprint for a recorded element (docs/06-ai-pipeline.md step 4).

Order, most robust first: test id → role + name → label → placeholder → short unique text →
css → xpath. Uniqueness comes from the DOM at record time (``is_unique``); a locator that
wasn't unique then is left out, because the runner requires exactly one match.
"""

import json
from typing import Any

from .recording import Element

MAX_NAME_LEN = 80  # longer accessible names are usually whole containers, and fragile
MAX_TEXT_LEN = 50
# Playwright's getByTestId reads one attribute; the others become attribute css selectors.
TESTID_ATTR = "data-testid"
OTHER_TEST_ATTRS = ("data-test", "data-qa", "data-cy")
# Roles whose text is what the user typed, not a stable label.
TEXT_ENTRY_ROLES = {"textbox", "searchbox", "spinbutton", "combobox"}

Locator = dict[str, Any]


def build_locators(el: Element) -> list[Locator]:
    unique = el.is_unique
    locators: list[Locator] = []

    testid = el.attrs.get(TESTID_ATTR)
    if testid and unique.testid:
        locators.append({"kind": "testid", "value": testid})
    for attr in OTHER_TEST_ATTRS:
        value = el.attrs.get(attr)
        if value:  # uniqueness unknown for these: the runner skips non-unique matches
            locators.append({"kind": "css", "value": f"[{attr}={json.dumps(value)}]"})

    name = el.accessible_name
    if el.role and name and len(name) <= MAX_NAME_LEN and unique.role_name:
        locators.append({"kind": "role", "role": el.role, "name": name, "exact": True})

    if el.label_text and unique.label:
        locators.append({"kind": "label", "value": el.label_text, "exact": True})

    placeholder = el.attrs.get("placeholder")
    if placeholder:
        locators.append({"kind": "placeholder", "value": placeholder, "exact": True})

    text = el.text
    if text and len(text) <= MAX_TEXT_LEN and unique.text and el.role not in TEXT_ENTRY_ROLES:
        locators.append({"kind": "text", "value": text, "exact": True})

    if el.css_path and unique.css:
        locators.append({"kind": "css", "value": el.css_path})

    # XPath can't cross shadow roots; css (Playwright) pierces open ones.
    if el.xpath and not el.shadow_hosts:
        locators.append({"kind": "xpath", "value": el.xpath})

    if not locators:  # nothing unique was recorded: the css path still beats no target
        locators.append({"kind": "css", "value": el.css_path})
    return _dedupe(locators)


def _dedupe(locators: list[Locator]) -> list[Locator]:
    seen: set[str] = set()
    out = []
    for loc in locators:
        key = json.dumps(loc, sort_keys=True)
        if key not in seen:
            seen.add(key)
            out.append(loc)
    return out


def build_fingerprint(el: Element, frame_path: list[str]) -> dict[str, Any]:
    """Recorded descriptor for L2 fuzzy matching (docs/08-runner-and-self-healing.md)."""
    attributes = {k: v for k, v in el.attrs.items() if v is not None}
    if el.id:
        attributes["id"] = el.id
    if el.classes:
        attributes["class"] = " ".join(el.classes)
    fingerprint: dict[str, Any] = {
        "tag": el.tag,
        "role": el.role,
        "accessible_name": el.accessible_name,
        "text": el.text,
        "attributes": attributes,
        "nearby_text": el.nearby_text,
        "frame_path": frame_path,
    }
    vw, vh = el.viewport
    if vw > 0 and vh > 0:
        x, y, w, h = el.bbox
        fingerprint["bbox_norm"] = [
            round(min(max(v, 0.0), 1.0), 4) for v in (x / vw, y / vh, w / vw, h / vh)
        ]
    return fingerprint


def build_target(el: Element, frame_path: list[str]) -> dict[str, Any]:
    return {"locators": build_locators(el), "fingerprint": build_fingerprint(el, frame_path)}
