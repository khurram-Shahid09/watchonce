"""Build a workflow spec from normalized candidates and the Understand result
(docs/06-ai-pipeline.md steps 4-5). Deterministic: the AI decides meaning (intents, inputs,
checkpoints); locators, values and structure come from the recording.

Safety rules applied here regardless of what the AI said:
- a masked (``__SECRET__``) value is always a secret reference, never a constant;
- clicks and key presses whose intent or element name is a risky verb get a checkpoint;
- the first navigation is always kept.
"""

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from engine.llm.types import StepUnderstanding, Understanding
from engine.spec.validate import RISKY_VERBS

IDENT = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
MASK = "__SECRET__"
_RISKY = re.compile(rf"\b({'|'.join(RISKY_VERBS)})\w*\b", re.IGNORECASE)
_DATE_HINT = re.compile(r"^(?=.*Y)(?=.*M)(?=.*D)[YMD/.\- ]{6,12}$")
_US_DATE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DECIMALS = re.compile(r"^-?\d+\.(\d+)$")
VALUE_ACTIONS = {"fill", "select"}
CHECKPOINT_ACTIONS = {"click", "press"}
BODY_TARGET = {"locators": [{"kind": "css", "value": "body"}]}


def check(candidates: list[dict[str, Any]], u: Understanding) -> list[str]:
    """Problems that make the answer unusable. Sent back to the model for one retry."""
    problems: list[str] = []
    ids = [c["id"] for c in candidates]
    by_id = {c["id"]: c for c in candidates}
    got = [s.candidate_id for s in u.steps]
    if got != ids:
        missing = [i for i in ids if i not in got]
        unknown = [i for i in got if i not in by_id]
        if missing:
            problems.append(f"steps is missing candidates {', '.join(missing)}")
        if unknown:
            problems.append(f"steps has unknown candidate ids {', '.join(unknown)}")
        if not missing and not unknown:
            problems.append("steps must list every candidate once, in the given order")
        return problems

    inputs = {i.name for i in u.inputs}
    for name in inputs:
        if not IDENT.match(name):
            problems.append(f'input name "{name}" must be snake_case (a-z, 0-9, _)')
    if len(inputs) != len(u.inputs):
        problems.append("input names must be unique")
    if u.steps and not u.steps[0].keep:
        problems.append(f"{ids[0]} (the first navigation) must be kept")

    for step in u.steps:
        c = by_id[step.candidate_id]
        src = step.value_source
        if not step.intent.strip():
            problems.append(f"{c['id']}: intent is empty")
        if c["action"] in VALUE_ACTIONS and step.keep:
            if src.kind == "none":
                problems.append(f"{c['id']}: a {c['action']} step needs a value_source")
            if c.get("value") == MASK and src.kind != "secret":
                problems.append(f"{c['id']}: the value is masked, so value_source must be a secret")
            elif MASK in (c.get("value") or "") and src.kind == "constant":
                problems.append(
                    f"{c['id']}: part of the value is masked, so it can't be a constant; "
                    "use an input or a secret"
                )
        if src.kind == "input" and src.input_name not in inputs:
            problems.append(f'{c["id"]}: input "{src.input_name}" is not declared in inputs')
        if src.kind == "secret" and not (
            IDENT.match(src.secret_name) and IDENT.match(src.secret_field)
        ):
            problems.append(f"{c['id']}: secret_name and secret_field must be snake_case")

    for out in u.outputs:
        if not IDENT.match(out.name):
            problems.append(f'output name "{out.name}" must be snake_case')
        if out.after_candidate_id not in by_id:
            problems.append(f'output "{out.name}": unknown after_candidate_id')
        if out.from_candidate_id and out.from_candidate_id not in by_id:
            problems.append(f'output "{out.name}": unknown from_candidate_id')
        if out.pattern:
            try:
                re.compile(out.pattern)
            except re.error:
                problems.append(f'output "{out.name}": pattern is not a valid regular expression')
    return problems


def _date_format(hint: str, recorded: str) -> str | None:
    hint = hint.strip().upper()
    if _DATE_HINT.match(hint):
        return hint
    if _US_DATE.match(recorded):
        return "MM/DD/YYYY"
    if _ISO_DATE.match(recorded):
        return "YYYY-MM-DD"
    return None


def _value_template(
    c: dict[str, Any], step: StepUnderstanding, inputs: dict[str, Any]
) -> tuple[str, str | None]:
    """(template, secret) for a fill/select candidate; secret is "name.field" when used."""
    recorded = c.get("option_label") or c.get("value") or ""
    src = step.value_source
    if c.get("value") == MASK or src.kind == "secret":
        name = src.secret_name if IDENT.match(src.secret_name) else "login"
        fld = src.secret_field if IDENT.match(src.secret_field) else "password"
        return f"{{{{secrets.{name}.{fld}}}}}", f"{name}.{fld}"
    if src.kind == "input":
        spec_input = inputs[src.input_name]
        filters = ""
        if spec_input.type == "date":
            fmt = _date_format(spec_input.format_hint, recorded)
            filters = f' | date:"{fmt}"' if fmt else ""
        elif spec_input.type == "number" and (m := _DECIMALS.match(recorded)):
            filters = f" | number:{len(m.group(1))}"
        return f"{{{{{src.input_name}{filters}}}}}", None
    return recorded, None  # constant: replay exactly what was recorded


def _url_pattern(url: str) -> str:
    """Path glob for a url_matches check: segments with digits (ids) become ``*``."""
    path = urlsplit(url).path or "/"
    return "/".join("*" if re.search(r"\d", seg) else seg for seg in path.split("/"))


def _example(type_: str, raw: str) -> Any:
    try:
        if type_ == "number":
            return float(raw)
        if type_ == "integer":
            return int(raw)
    except ValueError:
        return raw
    if type_ == "boolean":
        return raw.strip().lower() in ("true", "yes", "1", "on")
    return raw


def assemble(
    candidates: list[dict[str, Any]],
    u: Understanding,
    *,
    recording_id: str,
    compiled_by: str,
) -> tuple[dict[str, Any], list[str]]:
    by_step = {s.candidate_id: s for s in u.steps}
    inputs_by_name = {i.name: i for i in u.inputs}
    warnings = list(u.warnings)
    steps: list[dict[str, Any]] = []
    produced_after: dict[str, int] = {}  # candidate id -> index in steps of its last step
    used_inputs: set[str] = set()
    secrets: dict[str, list[str]] = {}
    hosts: list[str] = []

    for n, c in enumerate(candidates):
        for url in (c.get("url"), c.get("navigates_to")):
            host = urlsplit(url or "").netloc.lower()
            if host and host not in hosts:
                hosts.append(host)
        meaning = by_step[c["id"]]
        if not meaning.keep and n > 0:
            warnings.append(
                f"Left out recorded step {c['id']}: {meaning.drop_reason or 'not needed'}"
            )
            produced_after[c["id"]] = len(steps) - 1
            continue

        step: dict[str, Any] = {
            "id": "",
            "action": c["action"],
            "intent": meaning.intent.strip()[:300],
        }
        action = c["action"]
        if action == "navigate":
            step["url"] = c["url"]
        else:
            if c.get("target"):
                step["target"] = c["target"]
            if action in VALUE_ACTIONS:
                template, secret = _value_template(c, meaning, inputs_by_name)
                if secret:
                    name, fld = secret.split(".")
                    if fld not in secrets.setdefault(name, []):
                        secrets[name].append(fld)
                if meaning.value_source.kind == "input" and not secret:
                    used_inputs.add(meaning.value_source.input_name)
                if action == "fill":
                    step["value"] = template
                elif c.get("option_label") or meaning.value_source.kind != "constant":
                    step["label"] = template
                else:
                    step["value"] = template
            if action == "press":
                step["key"] = c.get("key") or "Enter"

        name = (c.get("element") or {}).get("name") or ""
        risky = action in CHECKPOINT_ACTIONS and bool(_RISKY.search(f"{step['intent']} {name}"))
        if meaning.checkpoint or risky:
            reason = meaning.checkpoint_reason.strip() or "This step commits a change."
            step["checkpoint"] = {"type": "approval", "reason": reason[:500]}

        if action != "navigate":
            if meaning.assert_text_after.strip():
                step["assert_after"] = {
                    "type": "text_visible",
                    "value": meaning.assert_text_after.strip()[:300],
                }
            elif c.get("navigates_to"):
                step["assert_after"] = {
                    "type": "url_matches",
                    "value": _url_pattern(c["navigates_to"]),
                }
        if c.get("frame_ref"):
            step["screenshot_ref"] = c["frame_ref"]
        steps.append(step)
        produced_after[c["id"]] = len(steps) - 1

    # Extract steps go right after the step that makes the value appear.
    by_id = {c["id"]: c for c in candidates}
    outputs = []
    for out in sorted(
        u.outputs, key=lambda o: produced_after.get(o.after_candidate_id, -1), reverse=True
    ):
        source = by_id.get(out.from_candidate_id) if out.from_candidate_id else None
        extract: dict[str, Any] = {
            "id": "",
            "action": "extract",
            "intent": (out.description or f"Read the {out.name.replace('_', ' ')}")[:300],
            "target": (source or {}).get("target") or BODY_TARGET,
            "output": out.name,
        }
        if out.pattern:
            extract["pattern"] = out.pattern
        steps.insert(produced_after.get(out.after_candidate_id, len(steps) - 1) + 1, extract)
        outputs.append({"name": out.name, "type": out.type, "description": out.description[:500]})
    outputs.reverse()

    for n, step in enumerate(steps, start=1):
        step["id"] = f"s{n}"

    spec_inputs = []
    for i in u.inputs:
        if i.name not in used_inputs:
            continue
        item: dict[str, Any] = {"name": i.name, "type": i.type, "required": True}
        if i.example:
            item["example"] = _example(i.type, i.example)
        if i.description:
            item["description"] = i.description[:500]
        if i.format_hint:
            item["format_hint"] = i.format_hint[:200]
        spec_inputs.append(item)

    start = next((c["url"] for c in candidates if c["action"] == "navigate"), "")
    spec = {
        "spec_version": "1.0",
        "name": (u.workflow_name.strip() or "Recorded workflow")[:200],
        "description": u.summary.strip()[:2000],
        "allowed_domains": hosts,
        "start_url": start,
        "inputs": spec_inputs,
        "secrets": [{"name": k, "fields": v} for k, v in secrets.items()],
        "outputs": outputs,
        "steps": steps,
        "settings": {
            "default_timeout_ms": 15000,
            "heal_policy": "approve",
            "auto_approve_heal_min_confidence": 0.9,
            "slow_mo_ms": 0,
        },
        "source": {
            "recording_id": recording_id,
            "compiled_by": compiled_by,
            "compiled_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    }
    return spec, warnings
