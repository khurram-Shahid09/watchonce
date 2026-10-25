"""Starting runs: validate inputs against the spec and check the secrets it needs exist."""

from datetime import date
from typing import Any

from secrets_vault.models import Secret


def clean_inputs(
    spec: dict[str, Any], raw: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, str]]:
    """(values, errors). Values are typed per the spec: number → float, date → ISO string."""
    values: dict[str, Any] = {}
    errors: dict[str, str] = {}
    declared = {i["name"]: i for i in spec.get("inputs", [])}
    for name in raw:
        if name not in declared:
            errors[name] = "This workflow has no such input."
    for name, info in declared.items():
        value = raw.get(name)
        if value is None or (isinstance(value, str) and not value.strip()):
            if info.get("required", True):
                errors[name] = "Required."
            continue
        kind = info["type"]
        try:
            if kind == "number":
                values[name] = float(value)
            elif kind == "integer":
                if isinstance(value, float) and not value.is_integer():
                    raise ValueError
                values[name] = int(value)
            elif kind == "boolean":
                if isinstance(value, bool):
                    values[name] = value
                elif str(value).lower() in ("true", "yes", "1", "on", "false", "no", "0", "off"):
                    values[name] = str(value).lower() in ("true", "yes", "1", "on")
                else:
                    raise ValueError
            elif kind == "date":
                values[name] = date.fromisoformat(str(value).strip()).isoformat()
            else:
                text = str(value)
                if len(text) > 4000:
                    raise ValueError
                values[name] = text
        except (TypeError, ValueError):
            hint = {
                "number": "a number, e.g. 1250.50",
                "integer": "a whole number",
                "boolean": "true or false",
                "date": "a date as YYYY-MM-DD",
                "string": "text up to 4000 characters",
            }[kind]
            errors[name] = f"Expected {hint}."
    return values, errors


def missing_secrets(org, spec: dict[str, Any]) -> list[str]:
    """``name.field`` the spec needs that the workspace doesn't have."""
    have = {s.name: set(s.fields) for s in Secret.objects.for_org(org)}
    missing = []
    for ref in spec.get("secrets", []):
        for field in ref["fields"]:
            if field not in have.get(ref["name"], set()):
                missing.append(f"{ref['name']}.{field}")
    return missing
