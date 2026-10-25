"""Deterministic stand-in for the AI (``LLM_PROVIDER=fake``): tests, CI and offline work.

It applies the same rules the prompt asks for, mechanically: masked values become a login
secret, typed and chosen values become inputs, risky verbs get checkpoints. Good enough to
exercise the whole pipeline; not a substitute for the real Understand stage.
"""

import re
from typing import Any
from urllib.parse import urlsplit

from engine.compiler.sop import render_basic_sop
from engine.spec.validate import RISKY_VERBS

from .types import (
    InputUnderstanding,
    SopRequest,
    SopResult,
    StepUnderstanding,
    Understanding,
    UnderstandRequest,
    Usage,
    ValueSource,
)

_RISKY = re.compile(rf"\b({'|'.join(RISKY_VERBS)})\w*\b", re.IGNORECASE)
_DATE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")
_LOGIN_HINTS = ("user", "email", "login", "account")


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    if not slug or not slug[0].isalpha():
        slug = f"field_{slug}" if slug else "value"
    return slug[:60]


def _label(c: dict[str, Any]) -> str:
    el = c.get("element") or {}
    return el.get("label") or el.get("name") or el.get("text") or el.get("tag") or "field"


class FakeProvider:
    name = "fake"
    model = "fake-understand-v1"

    def understand(self, req: UnderstandRequest) -> tuple[Understanding, Usage]:
        steps: list[StepUnderstanding] = []
        inputs: dict[str, InputUnderstanding] = {}
        has_password = any(c.get("value_masked") for c in req.candidates)
        host = ""
        for c in req.candidates:
            action, label = c["action"], _label(c)
            host = host or urlsplit(c.get("url", "")).hostname or ""
            source = ValueSource(kind="none", input_name="", secret_name="", secret_field="")
            if action == "navigate":
                intent = f"Open {urlsplit(c['url']).path or '/'}"
            elif action == "fill":
                intent = f"Enter {label}"
                value = c.get("value") or ""
                if c.get("value_masked") or (
                    has_password and any(h in label.lower() for h in _LOGIN_HINTS)
                ):
                    field = "password" if c.get("value_masked") else "username"
                    source = ValueSource(
                        kind="secret",
                        input_name="",
                        secret_name=f"{_slug(host.split('.')[0] or 'app')}_login",
                        secret_field=field,
                    )
                else:
                    name = _slug(label)
                    source = ValueSource(
                        kind="input", input_name=name, secret_name="", secret_field=""
                    )
                    inputs.setdefault(name, _input(name, label, value))
            elif action == "select":
                intent = f"Choose {label}"
                name = _slug(label)
                source = ValueSource(kind="input", input_name=name, secret_name="", secret_field="")
                inputs.setdefault(
                    name, _input(name, label, c.get("option_label") or c.get("value") or "")
                )
            elif action == "press":
                intent = f"Press {c.get('key')}"
            elif action in ("check", "uncheck"):
                intent = f"{action.capitalize()} {label}"
            else:
                intent = f"Click {label}"
            risky = action in ("click", "press") and bool(_RISKY.search(label))
            steps.append(
                StepUnderstanding(
                    candidate_id=c["id"],
                    keep=True,
                    drop_reason="",
                    intent=intent[:300],
                    value_source=source,
                    checkpoint=risky,
                    checkpoint_reason=f"{label} commits a change" if risky else "",
                    assert_text_after="",
                )
            )
        name = (req.description.strip().splitlines() or ["Recorded workflow"])[0][:120]
        result = Understanding(
            workflow_name=name or "Recorded workflow",
            summary=req.description.strip()[:500],
            steps=steps,
            inputs=list(inputs.values()),
            outputs=[],
            warnings=["Compiled by the offline stand-in (LLM_PROVIDER=fake); review the steps."],
        )
        return result, Usage(provider=self.name, model=self.model, stop_reason="end_turn")

    def write_sop(self, req: SopRequest) -> tuple[SopResult, Usage]:
        return SopResult(markdown=render_basic_sop(req.spec)), Usage(
            provider=self.name, model=self.model, stop_reason="end_turn"
        )


def _input(name: str, label: str, example: str) -> InputUnderstanding:
    if _DATE.match(example):
        month, day, year = _DATE.match(example).groups()  # type: ignore[union-attr]
        return InputUnderstanding(
            name=name, type="date", example=f"{year}-{int(month):02d}-{int(day):02d}",
            description=label, format_hint="MM/DD/YYYY",
        )  # fmt: skip
    if _NUMBER.match(example):
        return InputUnderstanding(
            name=name, type="number", example=example, description=label, format_hint=""
        )
    return InputUnderstanding(
        name=name, type="string", example=example, description=label, format_hint=""
    )
