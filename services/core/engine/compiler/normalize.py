"""Normalize raw recorder events into candidate steps (docs/06-ai-pipeline.md step 1).

Deterministic and conservative: it only removes what can't matter for replay, and every
removal is counted in ``stats.dropped`` so a surprising result can be explained.

- typing into one field (several flushes) → one ``fill`` with the final value
- a click that only focused a field, opened a native select or toggled a checkbox → dropped
  (the fill / select / check that follows is the step)
- custom dropdown: click on a combobox, then on an option → one ``select`` by option label
- repeated clicks within 500 ms and double clicks → one click
- clicks on page containers (no role, long or no text) → dropped as noise
- navigations right after an action → ``navigates_to`` on that action; redirect chains
  collapse; navigations no action caused become ``navigate`` steps
- form ``submit`` events and Tab presses → dropped (the click / Enter is the step)
- the submit-button click a browser fires itself right after Enter in a form → dropped
- typed then fully cleared → dropped
"""

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Literal

from .locators import build_target
from .recording import Element, Event, Recording

REPEAT_CLICK_MS = 500
IMPLICIT_SUBMIT_MS = 50  # Enter in a form: the browser clicks its submit button itself
NAV_CAUSE_WINDOW_MS = 10_000
REDIRECT_MS = 3_000
NOISE_TEXT_LEN = 60
CONTAINER_TAGS = {
    "html", "body", "main", "div", "section", "article", "header", "footer", "aside", "nav",
    "form", "fieldset", "span", "p", "ul", "ol", "li", "table", "tbody", "thead", "tr", "td",
    "th", "label", "img", "svg",
}  # fmt: skip
OPTION_ROLES = {"option", "menuitem", "menuitemradio", "treeitem"}
CAUSING_ACTIONS = {"click", "press", "select", "check", "uncheck"}

Action = Literal["navigate", "click", "fill", "select", "check", "uncheck", "press"]


@dataclass
class _Item:
    action: Action
    url: str
    ts: int
    element: Element | None = None
    frame_path: list[str] = field(default_factory=list)
    value: str | None = None
    value_masked: bool = False
    values: list[str] = field(default_factory=list)  # every flushed value of a fill
    option_label: str | None = None
    option: Element | None = None
    key: str | None = None
    frame_ref: str | None = None
    navigates_to: str | None = None
    seqs: list[int] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _page(url: str) -> str:
    return url.split("#", 1)[0]


def _same_element(a: _Item, b: _Item) -> bool:
    return (
        a.element is not None
        and b.element is not None
        and a.element.css_path == b.element.css_path
        and a.frame_path == b.frame_path
        and _page(a.url) == _page(b.url)
    )


def normalize(recording: Recording) -> dict[str, Any]:
    events = recording.events
    dropped: Counter[str] = Counter()
    warnings = list(
        dict.fromkeys(recording.recording.warnings + [e.warning for e in events if e.warning])
    )

    items = _collect(events, dropped)
    items = _attribute_navigation(items, recording, dropped)
    items = _fold_into_next(items, dropped)
    items = _merge_custom_dropdowns(items, dropped)
    items = [i for i in items if not _is_noise(i, dropped)]

    candidates = [_to_dict(f"c{n}", item) for n, item in enumerate(items, start=1)]
    return {
        "format_version": 1,
        "description": recording.recording.description,
        "start_url": next((c["url"] for c in candidates if c["action"] == "navigate"), ""),
        "stats": {
            "raw_events": len(events),
            "candidates": len(candidates),
            "dropped": dict(sorted(dropped.items())),
        },
        "warnings": warnings,
        "candidates": candidates,
    }


def _collect(events: list[Event], dropped: Counter[str]) -> list[_Item]:
    """One pass over raw events: merge typing and repeated clicks, drop non-actions."""
    items: list[_Item] = []
    for ev in events:
        last = items[-1] if items else None
        item = _Item(
            action="click",
            url=ev.url,
            ts=ev.ts,
            element=ev.element,
            frame_path=ev.frame_path,
            frame_ref=ev.frame_ref,
            seqs=[ev.seq],
        )
        match ev.type:
            case "warning" | "file_input":
                dropped["unsupported"] += 1
            case "submit":
                dropped["submit_event"] += 1
            case "press" if ev.key == "Tab":
                dropped["tab_press"] += 1
            case "navigate":
                item.action, item.element = "navigate", None
                items.append(item)
            case "input":
                item.action = "fill"
                value = ev.value or ""
                if last is not None and last.action == "fill" and _same_element(last, item):
                    last.value = value
                    last.values.append(value)
                    last.value_masked = last.value_masked or ev.value_masked
                    last.seqs.append(ev.seq)
                    last.ts = ev.ts
                    last.frame_ref = last.frame_ref or ev.frame_ref
                    dropped["merged_typing"] += 1
                else:
                    item.value, item.values, item.value_masked = value, [value], ev.value_masked
                    if ev.prefilled:
                        item.notes.append("prefilled")
                    items.append(item)
            case "click" if _implicit_submit(last, ev):
                dropped["implicit_submit_click"] += 1
            case "click" | "dblclick":
                if (
                    last is not None
                    and last.action == "click"
                    and _same_element(last, item)
                    and (ev.type == "dblclick" or ev.ts - last.ts <= REPEAT_CLICK_MS)
                ):
                    if ev.type == "dblclick" and "double_click" not in last.notes:
                        last.notes.append("double_click")
                    last.seqs.append(ev.seq)
                    last.ts = ev.ts
                    dropped["repeated_click"] += 1
                else:
                    if ev.type == "dblclick":
                        item.notes.append("double_click")
                    items.append(item)
            case "select":
                item.action = "select"
                item.value, item.option_label = ev.value, ev.option_label
                items.append(item)
            case "check" | "uncheck":
                item.action = ev.type
                items.append(item)
            case "press":
                item.action, item.key = "press", ev.key
                items.append(item)
    return [i for i in items if not _typed_then_cleared(i, dropped)]


def _implicit_submit(last: _Item | None, ev: Event) -> bool:
    el = ev.element
    return (
        last is not None
        and last.action == "press"
        and last.key == "Enter"
        and ev.ts - last.ts <= IMPLICIT_SUBMIT_MS
        and el is not None
        and (el.attrs.get("type") == "submit" or (el.tag == "button" and not el.attrs.get("type")))
    )


def _typed_then_cleared(item: _Item, dropped: Counter[str]) -> bool:
    # A lone "" is kept (clearing a prefilled field is a real step); text that was typed
    # and then removed again is not. Without the field's initial value this is a heuristic.
    if item.action == "fill" and item.value == "" and any(item.values[:-1]):
        dropped["typed_then_cleared"] += 1
        return True
    return False


def _attribute_navigation(
    items: list[_Item], recording: Recording, dropped: Counter[str]
) -> list[_Item]:
    out: list[_Item] = []
    page: str | None = None
    for item in items:
        if item.action != "navigate":
            out.append(item)
            continue
        prev = out[-1] if out else None
        if page is not None and _page(item.url) == page:
            dropped["same_page_navigation"] += 1  # e.g. only the fragment changed
        elif prev is not None and prev.action == "navigate" and item.ts - prev.ts <= REDIRECT_MS:
            prev.url, prev.ts = item.url, item.ts  # redirect chain: keep the final URL
            prev.seqs.extend(item.seqs)
            dropped["redirect"] += 1
        elif (
            prev is not None
            and prev.action in CAUSING_ACTIONS
            and item.ts - prev.ts <= NAV_CAUSE_WINDOW_MS
        ):
            prev.navigates_to = item.url  # a following redirect overwrites it with the final URL
            prev.seqs.extend(item.seqs)
            dropped["caused_navigation"] += 1
        else:
            out.append(item)
        page = _page(item.url)

    if not out or out[0].action != "navigate":
        start = recording.recording.startUrl or (items[0].url if items else "")
        if start:
            out.insert(0, _Item(action="navigate", url=start, ts=0, notes=["synthesized_start"]))
    return out


def _fold_into_next(items: list[_Item], dropped: Counter[str]) -> list[_Item]:
    """Drop a click whose effect is recorded by the next step on the same element:
    focusing a field before typing, opening a native select, toggling a checkbox."""
    out: list[_Item] = []
    for n, item in enumerate(items):
        nxt = items[n + 1] if n + 1 < len(items) else None
        if (
            item.action == "click"
            and item.navigates_to is None
            and nxt is not None
            and nxt.action in ("fill", "select", "check", "uncheck")
            and _same_element(item, nxt)
        ):
            nxt.frame_ref = item.frame_ref or nxt.frame_ref  # taken before the click: cleaner
            nxt.seqs = item.seqs + nxt.seqs
            dropped["focus_click"] += 1
            continue
        out.append(item)
    return out


def _merge_custom_dropdowns(items: list[_Item], dropped: Counter[str]) -> list[_Item]:
    out: list[_Item] = []
    skip = False
    for n, item in enumerate(items):
        if skip:
            skip = False
            continue
        nxt = items[n + 1] if n + 1 < len(items) else None
        el = item.element
        opt = nxt.element if nxt is not None else None
        if (
            item.action == "click"
            and item.navigates_to is None
            and el is not None
            and el.role == "combobox"
            and el.tag != "select"
            and nxt is not None
            and nxt.action == "click"
            and opt is not None
            and opt.role in OPTION_ROLES
            and (opt.accessible_name or opt.text)
        ):
            item.action = "select"
            item.option_label = opt.accessible_name or opt.text
            item.option = opt
            item.navigates_to = nxt.navigates_to
            item.seqs = item.seqs + nxt.seqs
            item.notes.append("custom_dropdown")
            dropped["dropdown_option_click"] += 1
            skip = True
        out.append(item)
    return out


def _is_noise(item: _Item, dropped: Counter[str]) -> bool:
    el = item.element
    if (
        item.action == "click"
        and item.navigates_to is None
        and el is not None
        and el.role is None
        and el.tag in CONTAINER_TAGS
        and not any(el.attrs.get(a) for a in ("data-testid", "data-test", "data-qa", "data-cy"))
        and (not el.text or len(el.text) > NOISE_TEXT_LEN)
    ):
        dropped["noise_click"] += 1
        return True
    return False


def _to_dict(candidate_id: str, item: _Item) -> dict[str, Any]:
    out: dict[str, Any] = {"id": candidate_id, "action": item.action, "url": item.url}
    if item.element is not None:
        el = item.element
        out["element"] = {
            "tag": el.tag,
            "role": el.role,
            "name": el.accessible_name,
            "label": el.label_text,
            "text": el.text,
            "nearby_text": el.nearby_text[:5],
        }
        out["target"] = build_target(el, item.frame_path)
    if item.action == "fill" or (item.action == "select" and item.value is not None):
        out["value"] = item.value
        out["value_masked"] = item.value_masked
    if item.option_label is not None:
        out["option_label"] = item.option_label
    if item.option is not None:
        out["option_target"] = build_target(item.option, item.frame_path)
    if item.key is not None:
        out["key"] = item.key
    if item.navigates_to is not None:
        out["navigates_to"] = item.navigates_to
    out["frame_ref"] = item.frame_ref
    out["source_seqs"] = item.seqs
    if item.notes:
        out["notes"] = item.notes
    return out
