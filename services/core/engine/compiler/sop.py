"""A plain SOP rendered straight from the spec. Used when the AI SOP call is unavailable
(and by the offline stand-in), so every workflow always has readable instructions.
Screenshots use the ``screenshot:<ref>`` form the AI SOP uses too; the dashboard resolves it."""

import re
from typing import Any

_REF = re.compile(r"\{\{\s*([^}|]+?)\s*(\|[^}]*)?\}\}")


def _human(template: str) -> str:
    def repl(m: re.Match[str]) -> str:
        ref = m.group(1)
        if ref.startswith("secrets."):
            _, name, field = ref.split(".")
            return f"the {field} for {name.replace('_', ' ')}"
        if ref.startswith("outputs."):
            return f"*{ref.split('.', 1)[1].replace('_', ' ')}*"
        return f"*{ref.replace('_', ' ')}*"

    return _REF.sub(repl, template)


def _cell(text: Any) -> str:
    return str(text if text is not None else "").replace("|", "\\|").replace("\n", " ")


def render_basic_sop(spec: dict[str, Any]) -> str:
    lines = [f"# {spec.get('name', 'Workflow')}", "", "## Purpose", ""]
    lines.append(spec.get("description") or "Repeat the recorded task.")
    lines += ["", "## Before you start", ""]
    lines.append(f"- Access to {', '.join(spec.get('allowed_domains', [])) or 'the application'}.")
    for secret in spec.get("secrets", []):
        lines.append(f"- The {secret['name'].replace('_', ' ')} ({', '.join(secret['fields'])}).")
    lines += ["", "## Information you need", ""]
    if spec.get("inputs"):
        lines += ["| Field | Description | Example |", "| --- | --- | --- |"]
        for i in spec["inputs"]:
            lines.append(
                f"| {_cell(i['name'].replace('_', ' '))} | {_cell(i.get('description', ''))} "
                f"| {_cell(i.get('example', ''))} |"
            )
    else:
        lines.append("(none)")
    lines += ["", "## Steps", ""]
    for n, step in enumerate(spec.get("steps", []), start=1):
        text = step["intent"]
        if "value" in step and step["action"] == "fill":
            text += f": {_human(step['value'])}"
        elif "label" in step:
            text += f": {_human(step['label'])}"
        elif step["action"] == "navigate":
            text += f" ({step['url']})"
        lines.append(f"{n}. {text}")
        if step.get("screenshot_ref"):
            lines.append(f"   ![Step {n}](screenshot:{step['screenshot_ref']})")
        if (step.get("checkpoint") or {}).get("type") == "approval":
            lines.append(
                f"   ⚠️ **Check before continuing:** {step['checkpoint'].get('reason', '')}"
            )
    lines += ["", "## Result", ""]
    outputs = spec.get("outputs", [])
    if outputs:
        lines.append("Record: " + ", ".join(o["name"].replace("_", " ") for o in outputs) + ".")
    else:
        lines.append("The last step completes without errors.")
    lines += [
        "",
        "## If something goes wrong",
        "",
        "- If a page looks different from the screenshots, stop and check you are in the right place.",
        "- If the form rejects a value, check its format against the examples above.",
        "",
    ]
    return "\n".join(lines)
