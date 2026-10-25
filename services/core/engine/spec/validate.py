"""Workflow spec validation: JSON Schema first, then semantic rules (docs/05-workflow-spec.md).

Errors block saving/running. Warnings are shown to the user but don't block.
"""

import json
import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator

from . import templating
from .models import WorkflowSpec

SCHEMA_PATH = Path(__file__).resolve().parents[4] / "packages" / "spec" / "workflow.schema.json"

# Intents with these verbs should be approval checkpoints (docs/06-ai-pipeline.md).
RISKY_VERBS = (
    "submit",
    "pay",
    "approve",
    "delete",
    "remove",
    "send",
    "publish",
    "transfer",
    "confirm",
)
_RISKY_RE = re.compile(rf"\b({'|'.join(RISKY_VERBS)})\w*\b", re.IGNORECASE)
_TEMPLATED_FIELDS = ("url", "value", "label")


@dataclass(frozen=True)
class Issue:
    path: str  # JSON-pointer-ish, e.g. "steps/3/value"
    message: str


@dataclass
class ValidationResult:
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    spec: WorkflowSpec | None = None

    @property
    def ok(self) -> bool:
        return not self.errors


@cache
def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf8"))


@cache
def _validator() -> Draft202012Validator:
    schema = load_schema()
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


def _pointer(parts: Any) -> str:
    return "/".join(str(p) for p in parts) or "/"


def host_allowed(netloc: str, allowed_domains: list[str]) -> bool:
    """``netloc`` is host[:port]. Entries match exactly, ``*.x.com`` matches subdomains of x.com.

    An entry without a port matches any port; an entry with a port must match it.
    """
    host, _, port = netloc.lower().partition(":")
    for entry in allowed_domains:
        e_host, _, e_port = entry.lower().partition(":")
        if e_port and e_port != port:
            continue
        if e_host.startswith("*."):
            if host.endswith(e_host[1:]):
                return True
        elif host == e_host:
            return True
    return False


def _check_url(url: str, path: str, allowed: list[str], errors: list[Issue]) -> None:
    # Template expressions may appear in the path/query, never in the scheme or host.
    parts = urlsplit(url)
    if templating.has_expressions(parts.scheme + parts.netloc):
        errors.append(Issue(path, "URL scheme and host cannot be templated"))
        return
    if parts.scheme not in ("http", "https") or not parts.netloc:
        errors.append(Issue(path, "URL must be absolute http(s)"))
        return
    if not host_allowed(parts.netloc, allowed):
        errors.append(Issue(path, f'host "{parts.netloc}" is not in allowed_domains'))


def _semantic_checks(spec: dict[str, Any], result: ValidationResult) -> None:
    errors, warnings = result.errors, result.warnings
    allowed = spec["allowed_domains"]

    def unique(items: list[dict[str, Any]], key: str, label: str) -> set[str]:
        seen: set[str] = set()
        for i, item in enumerate(items):
            if item[key] in seen:
                errors.append(Issue(f"{label}/{i}/{key}", f'duplicate {label[:-1]} "{item[key]}"'))
            seen.add(item[key])
        return seen

    input_names = unique(spec["inputs"], "name", "inputs")
    output_names = unique(spec["outputs"], "name", "outputs")
    unique(spec["steps"], "id", "steps")
    secrets = {s["name"]: set(s["fields"]) for s in spec["secrets"]}
    unique(spec["secrets"], "name", "secrets")

    _check_url(spec["start_url"], "start_url", allowed, errors)

    produced: dict[str, int] = {}
    for i, step in enumerate(spec["steps"]):
        base = f"steps/{i}"

        for fname in _TEMPLATED_FIELDS:
            if fname not in step:
                continue
            try:
                refs = templating.parse(step[fname])
            except templating.TemplateError as exc:
                errors.append(Issue(f"{base}/{fname}", str(exc)))
                continue
            for ref in refs:
                if ref.kind == "input" and ref.name not in input_names:
                    errors.append(Issue(f"{base}/{fname}", f'unknown input "{ref.name}"'))
                elif ref.kind == "secret" and ref.field not in secrets.get(ref.name, set()):
                    errors.append(
                        Issue(f"{base}/{fname}", f'unknown secret "{ref.name}.{ref.field}"')
                    )
                elif ref.kind == "output" and ref.name not in produced:
                    errors.append(
                        Issue(
                            f"{base}/{fname}", f'output "{ref.name}" is used before it is extracted'
                        )
                    )
            if (
                fname == "url"
                and step["action"] == "navigate"
                and any(r.kind == "secret" for r in refs)
            ):
                errors.append(Issue(f"{base}/url", "secrets cannot be used in URLs"))

        if step["action"] == "navigate":
            _check_url(step["url"], f"{base}/url", allowed, errors)

        if step["action"] == "extract":
            out = step["output"]
            if out not in output_names:
                errors.append(Issue(f"{base}/output", f'output "{out}" is not declared in outputs'))
            elif out in produced:
                errors.append(
                    Issue(
                        f"{base}/output",
                        f'output "{out}" is already produced by steps/{produced[out]}',
                    )
                )
            produced.setdefault(out, i)
            if "pattern" in step:
                try:
                    re.compile(step["pattern"])
                except re.error as exc:
                    errors.append(Issue(f"{base}/pattern", f"invalid regex: {exc}"))

        target = step.get("target")
        if target is not None and len(target["locators"]) < 2:
            warnings.append(Issue(f"{base}/target", "only one locator; self-healing is weaker"))

        is_checkpoint = step.get("checkpoint", {}).get("type") == "approval"
        if (
            not is_checkpoint
            and step["action"] in ("click", "press")
            and _RISKY_RE.search(step["intent"])
        ):
            warnings.append(
                Issue(
                    base, f'"{step["intent"]}" looks irreversible; consider an approval checkpoint'
                )
            )

    for i, out in enumerate(spec["outputs"]):
        if out["name"] not in produced:
            errors.append(Issue(f"outputs/{i}", f'output "{out["name"]}" is never extracted'))


def validate_spec(spec: Any) -> ValidationResult:
    """Validate a decoded spec. ``result.spec`` is the typed model when there are no errors."""
    result = ValidationResult()
    schema_errors = sorted(_validator().iter_errors(spec), key=lambda e: list(e.absolute_path))
    for err in schema_errors:
        result.errors.append(Issue(_pointer(err.absolute_path), err.message))
    if result.errors:
        return result

    _semantic_checks(spec, result)
    if result.ok:
        result.spec = WorkflowSpec.model_validate(spec)
    return result
