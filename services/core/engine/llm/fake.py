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
    RepairRequest,
    RepairResult,
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
FAKE_REPAIR_MARGIN = 0.05  # ahead of the runner-up, or it's a guess
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
        # A username is a login-looking field on the same page as a password (an email
        # typed into a form later on is an input, not the login).
        login_pages = {c.get("url") for c in req.candidates if c.get("value_masked")}
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
                    c.get("url") in login_pages and any(h in label.lower() for h in _LOGIN_HINTS)
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

    def repair(self, req: RepairRequest) -> tuple[RepairResult, Usage]:
        """The best-ranked candidate that can take the action, if it is reasonably similar
        and clearly ahead of the next one. No reasoning about the page, so it never guesses
        between look-alikes; the runner's own checks still apply."""
        usage = Usage(provider=self.name, model=self.model, stop_reason="end_turn")
        fitting = [c for c in req.candidates if c.get("fits_action", True)]
        for n, c in enumerate(fitting[:1]):
            runner_up = fitting[n + 1].get("score", 0) if len(fitting) > n + 1 else 0.0
            if c.get("score", 0) >= 0.5 and c.get("score", 0) - runner_up >= FAKE_REPAIR_MARGIN:
                return RepairResult(
                    decision="match",
                    candidate_id=c["id"],
                    confidence=min(0.95, float(c["score"]) + 0.15),
                    explanation=f"Closest match to the recorded element (similarity {c['score']:.2f}).",
                ), usage
        return RepairResult(
            decision="no_match",
            candidate_id="",
            confidence=0.0,
            explanation="Nothing on the page is clearly the recorded element.",
        ), usage


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
