"""The authoring agent: builds a workflow from plain instructions by doing the task once in a
real browser, one AI-chosen step at a time, while the user watches (docs/17-authoring-agent.md).

The guarantees are the same as for recordings and self-healing:
- the AI picks elements only by id from what is really on the page; anything else is refused;
- saved logins are typed from the vault; the AI sees their names, never their values, and
  secret values are scrubbed from everything it reads;
- a step that changes something for real (submit, pay, delete, post…) waits for a person;
- every step is saved like a compiled recording (locators + fingerprint), so the workflow
  later runs without AI and self-heals like any other.
"""

import base64
import contextlib
import logging
import re
import time
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

from django.conf import settings
from django.utils import timezone
from playwright.sync_api import Browser, BrowserContext, Locator, Page, Route
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from engine.compiler.locators import build_target
from engine.compiler.recording import Element
from engine.compiler.sop import render_basic_sop
from engine.llm.types import AuthorAction
from engine.runner.healer import AGENT_JS
from engine.runner.live_view import Screencast, install_cursor, point_at
from engine.runner.locate import ElementNotFound, find
from engine.spec.validate import RISKY_VERBS, host_allowed, validate_spec

log = logging.getLogger(__name__)

MAX_STEPS = 40
MAX_CALLS = 60
MAX_FAILURES_IN_A_ROW = 3
CANDIDATE_LIMIT = 80
PAGE_TEXT_CHARS = 4000
ACTION_TIMEOUT_MS = 15000
WAIT_TIMEOUT_MS = 45000
SETTLE_MS = 2000
HIGHLIGHT = "3px solid #f59e0b"
RETRY_PAUSES_S = (10, 20, 40)  # a busy or rate-limited AI: wait and try again
TARGET_ACTIONS = ("click", "fill", "select", "check", "uncheck")
_RISKY = re.compile(rf"\b({'|'.join(RISKY_VERBS)}|post|publish|buy|purchase|order)\w*\b", re.I)
_URL = re.compile(r"https?://[^\s\"'<>)]+")


class AuthorFailed(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class AuthorStopped(Exception):
    """Ended by a person or a limit: cancelled, timed out."""

    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class StepError(Exception):
    """One step didn't work; the AI hears about it and tries something else."""


class _StopAtRiskyStep(Exception):
    """The person declined a risky step: keep it in the workflow, but don't do it now."""


class Author:
    def __init__(self, session, browser: Browser, *, live=None, provider=None) -> None:
        from runs import live as default_live

        self.session = session
        self.browser = browser
        self.live = live or default_live
        self.provider = provider
        hosts = {urlsplit(session.start_url).netloc.lower()}
        hosts |= {urlsplit(u).netloc.lower() for u in _URL.findall(session.instructions)}
        self.hosts = sorted(h for h in hosts if h)
        self.allowed = [*self.hosts, *settings.RUNNER_EXTRA_ALLOWED_HOSTS]
        self.vault: dict[str, Any] = {}  # name -> Secret (values decrypted only to type them)
        self.secret_values: dict[str, dict[str, str]] = {}
        self.steps: list[dict[str, Any]] = []
        self.inputs: dict[str, dict[str, Any]] = {}
        self.outputs: dict[str, dict[str, Any]] = {}
        self.used_secrets: dict[str, set[str]] = {}
        self.history: list[dict[str, Any]] = []
        self.calls = 0
        self.cost = Decimal(0)
        self.blocked: list[str] = []
        self.screencast: Screencast | None = None
        self.name = ""
        self.summary = ""
        self.note = ""

    # --- events -------------------------------------------------------------------------

    def publish(self, event: dict[str, Any]) -> None:
        try:
            self.live.publish(self.session.id, event)
        except Exception:  # the live view is best effort
            log.warning("authoring %s: couldn't publish %s", self.session.id, event.get("type"))

    def _log(self, entry: dict[str, Any]) -> None:
        """The visible log of what the agent did (the session's ``steps``), and its event."""
        entries = self.session.steps
        index = next((n for n, e in enumerate(entries) if e["n"] == entry["n"]), None)
        if index is None:
            entries.append(entry)
        else:
            entries[index] = {**entries[index], **entry}
        self.session.save(update_fields=["steps", "updated_at"])
        self.publish({"type": "agent_step", **entry})

    def scrub(self, text: str) -> str:
        for values in self.secret_values.values():
            for value in values.values():
                if value and len(value) >= 3:
                    text = text.replace(value, "•••")
        return text

    # --- entry point --------------------------------------------------------------------

    def execute(self) -> None:
        from authoring.models import AuthoringSession

        status: str = AuthoringSession.Status.SUCCEEDED
        code, message = "", ""
        context: BrowserContext | None = None
        try:
            self._load_vault()
            context = self._new_context()
            page = context.new_page()
            self.screencast = Screencast(page, self.publish)
            self._open_start(page)
            try:
                self._loop(page)
            except _StopAtRiskyStep:
                self.note = (
                    "Saved. The last step wasn't done while building; it will ask for approval "
                    "on every run."
                )
            self._save()
        except AuthorStopped as stop:
            status, code, message = stop.status, stop.status, stop.message
        except AuthorFailed as failure:
            status, code, message = "failed", failure.code, self.scrub(failure.message)
        except Exception as exc:  # a bug or a browser crash: fail the session, keep the worker
            log.exception("authoring %s crashed", self.session.id)
            status, code, message = "failed", "internal_error", self.scrub(str(exc))[:2000]
        finally:
            if self.screencast is not None:
                self.screencast.stop()
            if context is not None:
                with contextlib.suppress(PlaywrightError):
                    context.close()
        self._finish(status, code, message)

    # --- setup --------------------------------------------------------------------------

    def _load_vault(self) -> None:
        from secrets_vault.models import Secret

        self.vault = {s.name: s for s in Secret.objects.for_org(self.session.org)}

    def _secret(self, name: str, field: str) -> str:
        if name not in self.secret_values:
            self.secret_values[name] = self.vault[name].values()
        return self.secret_values[name].get(field, "")

    def _new_context(self) -> BrowserContext:
        context = self.browser.new_context(
            viewport={"width": 1280, "height": 800},
            accept_downloads=False,
            permissions=[],
            locale="en-US",
        )
        context.set_default_timeout(ACTION_TIMEOUT_MS)
        context.route("**/*", self._guard)
        install_cursor(context)
        return context

    def _guard(self, route: Route) -> None:
        url = urlsplit(route.request.url)
        if url.scheme not in ("http", "https") or host_allowed(url.netloc, self.allowed):
            route.continue_()
            return
        self.blocked.append(url.netloc)
        route.abort("blockedbyclient")

    def _check_cancel(self) -> None:
        if self.live.cancel_requested(self.session.id):
            raise AuthorStopped("cancelled", "Cancelled by a user.")

    # --- the loop -----------------------------------------------------------------------

    def _open_start(self, page: Page) -> None:
        url = self.session.start_url
        n = 1
        self._log(
            {
                "n": n,
                "intent": f"Open {urlsplit(url).netloc}",
                "action": "navigate",
                "status": "running",
            }
        )
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except PlaywrightError as exc:
            raise AuthorFailed(
                "start_url_failed", f"Couldn't open {url}: {str(exc).splitlines()[0]}"
            ) from None
        self._settle(page)
        self.steps.append(
            {"id": "s1", "action": "navigate", "intent": f"Open {urlsplit(url).netloc}", "url": url}
        )
        self.history.append(
            {
                "step": 1,
                "intent": self.steps[0]["intent"],
                "action": "navigate",
                "result": "ok",
                "url": self.scrub(page.url),
            }
        )
        self._log({"n": n, "status": "ok"})

    def _loop(self, page: Page) -> None:
        failures = 0
        while True:
            self._check_cancel()
            if len(self.steps) >= MAX_STEPS:
                raise AuthorFailed(
                    "too_many_steps",
                    f"Stopped after {MAX_STEPS} steps. Split the task into smaller workflows.",
                )
            if self.calls >= MAX_CALLS:
                raise AuthorFailed(
                    "too_many_attempts",
                    "Stopped: too many attempts. Make the instructions more specific.",
                )
            candidates = self._candidates(page)
            decision = self._ask(page, candidates)
            if decision.status == "done":
                self.name, self.summary = decision.workflow_name.strip(), decision.summary.strip()
                return
            if decision.status == "stuck":
                raise AuthorFailed(
                    "agent_stuck",
                    decision.explanation
                    or "The agent couldn't work out the next step. Add more detail to the instructions.",
                )
            n = len(self.session.steps) + 1
            try:
                self._do(page, decision, candidates, n)
                failures = 0
            except StepError as err:
                failures += 1
                reason = self.scrub(str(err))[:500]
                self.history.append(
                    {
                        "intent": decision.intent,
                        "action": decision.action,
                        "result": f"error: {reason}",
                    }
                )
                self._log({"n": n, "status": "failed", "error": reason})
                if failures >= MAX_FAILURES_IN_A_ROW:
                    raise AuthorFailed(
                        "agent_failed",
                        f"{MAX_FAILURES_IN_A_ROW} steps in a row didn't work. Last problem: {reason}",
                    ) from None

    def _candidates(self, page: Page) -> list[dict[str, Any]]:
        try:
            page.evaluate(f"() => {{ {AGENT_JS}\n window.__watchonceAgent = __watchonceAgent; }}")
            return page.evaluate(
                "limit => window.__watchonceAgent.candidates(limit)", CANDIDATE_LIMIT
            )
        except PlaywrightError:
            return []  # mid-navigation: the AI sees an empty page and usually waits

    def _compact(self, c: dict[str, Any]) -> dict[str, Any]:
        d = c.get("descriptor") or {}
        attrs = d.get("attrs") or {}
        keep = {
            k: str(v)[:120]
            for k, v in attrs.items()
            if v and k in ("type", "name", "placeholder", "href", "aria-label", "title", "value")
        }
        if (attrs.get("type") or "").lower() == "password":
            keep.pop("value", None)
        out = {
            "id": c["id"],
            "tag": d.get("tag"),
            "role": d.get("role"),
            "name": (d.get("accessible_name") or "")[:120],
            "text": (d.get("text") or "")[:120],
            "label": d.get("label_text") or "",
            "attributes": keep,
            "enabled": c.get("enabled", True),
        }
        return {k: (self.scrub(v) if isinstance(v, str) else v) for k, v in out.items()}

    def _ask(self, page: Page, candidates: list[dict[str, Any]]) -> AuthorAction:
        from engine.llm import LLMError, get_provider, load_prompt
        from engine.llm.types import AuthorRequest, Image
        from metering.service import budget_left, cost_of, record_call

        org = self.session.org
        if not budget_left(org):
            raise AuthorFailed("ai_budget", "This workspace reached its monthly AI budget.")
        self.publish({"type": "thinking"})
        provider = self.provider or get_provider("author")
        _, prompt_version = load_prompt("author", provider.name)
        images = []
        with contextlib.suppress(PlaywrightError):
            images.append(
                Image(
                    label="now",
                    data=page.screenshot(type="jpeg", quality=60),
                    media_type="image/jpeg",
                )
            )
        try:
            text = page.inner_text("body", timeout=3000)
        except PlaywrightError:
            text = ""
        request = AuthorRequest(
            instructions=self.session.instructions,
            start_url=self.session.start_url,
            page_url=self.scrub(page.url),
            page_title=self.scrub(self._title(page)),
            candidates=[self._compact(c) for c in candidates],
            page_text=self.scrub(re.sub(r"\n\s*\n+", "\n", text))[:PAGE_TEXT_CHARS],
            history=self.history[-25:],
            secrets=[{"name": s.name, "fields": list(s.fields)} for s in self.vault.values()],
            images=images,
        )
        self.calls += 1
        for attempt, pause in enumerate((*RETRY_PAUSES_S, None)):
            try:
                result, usage = provider.author(request)
                break
            except LLMError as exc:
                if exc.usage is not None:
                    record_call(
                        org=org,
                        purpose="author",
                        usage=exc.usage,
                        entity_id=self.session.id,
                        prompt_version=prompt_version,
                        error_code=exc.code,
                    )
                if not exc.retryable or pause is None:
                    raise AuthorFailed(
                        "ai_error", f"The AI couldn't answer: {exc.message}"
                    ) from None
                # Busy or rate limited (free tiers allow a few calls a minute): wait, then retry.
                log.info(
                    "authoring %s: %s; retry %d in %ss",
                    self.session.id,
                    exc.message,
                    attempt + 1,
                    pause,
                )
                self.publish(
                    {"type": "thinking", "message": f"{exc.message} Trying again in {pause} s…"}
                )
                self._pause(pause)
        record_call(
            org=org,
            purpose="author",
            usage=usage,
            entity_id=self.session.id,
            prompt_version=prompt_version,
        )
        self.cost += cost_of(usage)
        return result

    def _pause(self, seconds: int) -> None:
        """Sleep, but stop promptly when someone cancels."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self._check_cancel()
            time.sleep(min(1.0, deadline - time.monotonic()))

    @staticmethod
    def _title(page: Page) -> str:
        try:
            return page.title()
        except PlaywrightError:
            return ""

    # --- one step -----------------------------------------------------------------------

    def _do(self, page: Page, d: AuthorAction, candidates: list[dict[str, Any]], n: int) -> None:
        action = d.action
        intent = (d.intent or action or "Step").strip()[:300]
        by_id = {c["id"]: c for c in candidates}
        cand = by_id.get(d.candidate_id) if d.candidate_id else None
        if action in TARGET_ACTIONS and cand is None:
            raise StepError(
                f"there is no element {d.candidate_id!r} on the page; choose an id from the list"
            )
        if not action:
            raise StepError("no action was given")
        if d.value_kind == "secret" and (
            d.secret_name not in self.vault
            or d.secret_field not in self.vault[d.secret_name].fields
        ):
            raise StepError(
                f"there's no saved login {d.secret_name!r} with a field {d.secret_field!r}"
            )

        step: dict[str, Any] = {"id": f"s{len(self.steps) + 1}", "action": action, "intent": intent}
        self._log(
            {
                "n": n,
                "intent": intent,
                "action": action,
                "status": "running",
                "explanation": d.explanation[:300],
            }
        )
        if self.screencast is not None:
            self.screencast.step_id = step["id"]
        locator = page.locator(f'[data-wo-candidate="{cand["id"]}"]') if cand else None
        if cand is not None:
            step["target"] = self._target(page, cand)

        name = ""
        if cand is not None:
            d_ = cand.get("descriptor") or {}
            name = d_.get("accessible_name") or d_.get("text") or ""
        if action in ("click", "press") and (d.risky or bool(_RISKY.search(name))):
            step["checkpoint"] = {
                "type": "approval",
                "reason": f"“{name or intent}” changes something for real.",
            }
            if not self._approve(page, locator, step, n):
                self.steps.append(step)
                self.history.append(
                    {
                        "step": len(self.steps),
                        "intent": intent,
                        "action": action,
                        "result": "kept, not done (declined)",
                    }
                )
                self._log(
                    {
                        "n": n,
                        "status": "skipped",
                        "error": "Not done while building: you declined it.",
                    }
                )
                raise _StopAtRiskyStep()

        try:
            read = self._perform(page, d, step, locator)
        except PlaywrightTimeout:
            if self.blocked:
                raise StepError(
                    f"the page tried to reach {self.blocked[-1]}, which isn't allowed"
                ) from None
            raise StepError("it didn't complete in time") from None
        except PlaywrightError as exc:
            raise StepError(str(exc).splitlines()[0]) from None

        if action not in ("wait_for", "extract"):
            self._settle(page)
        self.steps.append(step)
        entry: dict[str, Any] = {
            "step": len(self.steps),
            "intent": intent,
            "action": action,
            "result": "ok",
            "url": self.scrub(page.url),
        }
        if read is not None:
            entry["value_read"] = self.scrub(str(read))[:200]
        self.history.append(entry)
        self._log(
            {"n": n, "status": "ok", **({"value": entry["value_read"]} if read is not None else {})}
        )

    def _target(self, page: Page, cand: dict[str, Any]) -> dict[str, Any]:
        element = Element.model_validate(cand["descriptor"])
        return build_target(element, [])

    def _value(self, d: AuthorAction, step: dict[str, Any]) -> tuple[str, str]:
        """The text to type now; sets the step's value template."""
        if d.value_kind == "secret":
            self.used_secrets.setdefault(d.secret_name, set()).add(d.secret_field)
            return self._secret(
                d.secret_name, d.secret_field
            ), f"{{{{secrets.{d.secret_name}.{d.secret_field}}}}}"
        if d.value_kind == "input" and d.input_name:
            name = re.sub(r"[^a-z0-9_]", "_", d.input_name.lower()).strip("_")[:60] or "value"
            if not name[0].isalpha():
                name = f"v_{name}"
            self.inputs.setdefault(
                name,
                {
                    "name": name,
                    "type": "number" if d.input_type == "number" else "string",
                    "example": d.value,
                    "description": step["intent"][:500],
                },
            )
            return d.value, f"{{{{{name}}}}}"
        return d.value, d.value

    def _perform(
        self, page: Page, d: AuthorAction, step: dict[str, Any], locator: Locator | None
    ) -> Any:
        action = d.action
        if action == "click":
            point_at(page, locator, click=True)  # type: ignore[arg-type]
            locator.click(timeout=ACTION_TIMEOUT_MS)  # type: ignore[union-attr]
        elif action == "fill":
            now, template = self._value(d, step)
            if not now:
                raise StepError("there was no value to type")
            point_at(page, locator)  # type: ignore[arg-type]
            if d.value_kind == "secret" or len(now) > 200:
                locator.fill(now, timeout=ACTION_TIMEOUT_MS)  # type: ignore[union-attr]
            else:  # typed key by key, so the live view shows it
                locator.fill("", timeout=ACTION_TIMEOUT_MS)  # type: ignore[union-attr]
                locator.press_sequentially(now, delay=25, timeout=ACTION_TIMEOUT_MS)  # type: ignore[union-attr]
            step["value"] = template
        elif action == "select":
            now, template = self._value(d, step)
            point_at(page, locator, click=True)  # type: ignore[arg-type]
            self._select(page, locator, now)  # type: ignore[arg-type]
            step["label"] = template
        elif action in ("check", "uncheck"):
            point_at(page, locator, click=True)  # type: ignore[arg-type]
            (locator.check if action == "check" else locator.uncheck)(timeout=ACTION_TIMEOUT_MS)  # type: ignore[union-attr]
        elif action == "press":
            key = d.key or "Enter"
            if locator is not None:
                locator.press(key, timeout=ACTION_TIMEOUT_MS)
            else:
                page.keyboard.press(key)
            step["key"] = key
        elif action == "navigate":
            url = d.url.strip()
            if not url.startswith(("http://", "https://")):
                raise StepError("navigate needs an absolute http(s) URL")
            if not host_allowed(urlsplit(url).netloc, self.allowed):
                raise StepError(
                    f"{urlsplit(url).netloc} isn't one of the sites in the instructions"
                )
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            step["url"] = url
        elif action == "wait_for":
            text = d.wait_text.strip()
            if not text:
                raise StepError("wait_for needs wait_text")
            page.get_by_text(text).first.wait_for(state="visible", timeout=WAIT_TIMEOUT_MS)
            step["condition"] = {"type": "text_visible", "value": text}
            step["timeout_ms"] = WAIT_TIMEOUT_MS
        elif action == "extract":
            return self._extract(page, d, step)
        else:
            raise StepError(f"unknown action {action!r}")
        return None

    def _select(self, page: Page, locator: Locator, wanted: str) -> None:
        if locator.evaluate("e => e.tagName") == "SELECT":
            try:
                locator.select_option(label=wanted, timeout=ACTION_TIMEOUT_MS)
            except PlaywrightError:
                locator.select_option(value=wanted, timeout=ACTION_TIMEOUT_MS)
            return
        locator.click(timeout=ACTION_TIMEOUT_MS)
        try:
            option = find(
                page,
                [
                    {"kind": "role", "role": "option", "name": wanted, "exact": True},
                    {"kind": "role", "role": "menuitem", "name": wanted, "exact": True},
                    {"kind": "text", "value": wanted, "exact": True},
                ],
                5000,
            )
        except ElementNotFound:
            raise StepError(f"no option “{wanted}” to choose") from None
        point_at(page, option.locator, click=True)
        option.locator.click(timeout=ACTION_TIMEOUT_MS)

    def _extract(self, page: Page, d: AuthorAction, step: dict[str, Any]) -> Any:
        shown = d.value.strip()
        name = (
            re.sub(r"[^a-z0-9_]", "_", (d.output_name or "value").lower()).strip("_")[:60]
            or "value"
        )
        if not name[0].isalpha():
            name = f"v_{name}"
        if not shown:
            raise StepError("extract needs the value as it appears on the page")
        found = page.evaluate(
            """(want) => {
                for (const e of document.querySelectorAll('[data-wo-extract]')) e.removeAttribute('data-wo-extract');
                let best = null, len = Infinity;
                for (const el of document.querySelectorAll('body *')) {
                    if (el.closest('#__wo-cursor') || el.children.length > 40) continue;
                    const r = el.getBoundingClientRect();
                    if (r.width < 1 || r.height < 1) continue;
                    const t = (el.innerText || '').trim();
                    if (t && t.includes(want) && t.length < len) { best = el; len = t.length; }
                }
                if (!best) return false;
                best.setAttribute('data-wo-extract', '1');
                return true;
            }""",
            shown,
        )
        if not found:
            raise StepError(f"“{shown}” isn't on the page")
        holder = page.locator("[data-wo-extract]").first
        descriptor = holder.evaluate(
            f"el => {{ {AGENT_JS}\n return __watchonceAgent.describeOne(el); }}"
        )
        step["target"] = build_target(Element.model_validate(descriptor), [])
        point_at(page, holder)
        text = holder.inner_text()
        value: Any = text.strip()
        if d.pattern:
            try:
                match = re.search(d.pattern, text)
            except re.error:
                raise StepError(f"the pattern {d.pattern!r} isn't a valid regex") from None
            if match is None:
                raise StepError(f"the pattern {d.pattern!r} doesn't match “{text.strip()[:80]}”")
            value = match.group(0)
            step["pattern"] = d.pattern
        out_type = "number" if d.output_type == "number" else "string"
        if out_type == "number":
            try:
                value = float(str(value).replace(",", ""))
            except ValueError:
                raise StepError(
                    f"“{value}” isn't a number; give a pattern that picks the number"
                ) from None
        step["output"] = name
        self.outputs[name] = {"name": name, "type": out_type, "description": step["intent"][:500]}
        with contextlib.suppress(PlaywrightError):
            holder.evaluate("e => e.removeAttribute('data-wo-extract')")
        return value

    def _approve(self, page: Page, locator: Locator | None, step: dict[str, Any], n: int) -> bool:
        """Show the element and wait for the person: True = do it now, False = keep it undone."""
        from authoring.models import AuthoringSession

        session = self.session
        if locator is not None:
            point_at(page, locator)
            with contextlib.suppress(PlaywrightError):
                locator.evaluate(
                    f"e => {{ e.dataset.woOutline = e.style.outline; e.style.outline = '{HIGHLIGHT}'; }}"
                )
        with contextlib.suppress(PlaywrightError):
            jpeg = page.screenshot(type="jpeg", quality=60)
            self.publish(
                {
                    "type": "frame",
                    "step_id": step["id"],
                    "jpeg_b64": base64.b64encode(jpeg).decode(),
                }
            )
        question = {"n": n, "intent": step["intent"], "reason": step["checkpoint"]["reason"]}
        session.status, session.question = AuthoringSession.Status.AWAITING_APPROVAL, question
        session.save(update_fields=["status", "question", "updated_at"])
        self._log({"n": n, "status": "awaiting_approval"})
        self.publish({"type": "checkpoint", **question})
        decision = self.live.wait_for_decision(session.id, settings.RUN_CHECKPOINT_TIMEOUT_S)
        if locator is not None:
            with contextlib.suppress(PlaywrightError):
                locator.evaluate(
                    "e => { e.style.outline = e.dataset.woOutline || ''; delete e.dataset.woOutline; }"
                )
        session.status, session.question = AuthoringSession.Status.RUNNING, {}
        session.save(update_fields=["status", "question", "updated_at"])
        if decision is None:
            raise AuthorStopped("timed_out", "Nobody answered the approval in time.")
        if decision == "cancel":
            raise AuthorStopped("cancelled", "Cancelled by a user.")
        self.publish({"type": "approved", "n": n})
        self._log({"n": n, "status": "running"})
        return decision == "approve"

    def _settle(self, page: Page) -> None:
        try:
            page.wait_for_load_state("load", timeout=SETTLE_MS * 2)
            page.wait_for_load_state("networkidle", timeout=SETTLE_MS)
        except PlaywrightTimeout:
            pass

    # --- result -------------------------------------------------------------------------

    def _spec(self) -> dict[str, Any]:
        session = self.session
        base = session.base_version.spec if session.base_version_id else {}
        name = (
            self.name
            or base.get("name")
            or session.instructions.strip().splitlines()[0][:80]
            or "New workflow"
        )
        if base:
            name = base.get("name") or name
        return {
            "spec_version": "1.0",
            "name": name[:200],
            "description": (self.summary or base.get("description") or "")[:2000],
            "allowed_domains": self.hosts,
            "start_url": session.start_url,
            "inputs": list(self.inputs.values()),
            "secrets": [
                {"name": n, "fields": sorted(f)} for n, f in sorted(self.used_secrets.items())
            ],
            "outputs": list(self.outputs.values()),
            "steps": self.steps,
            "settings": base.get("settings") or {"default_timeout_ms": 15000},
        }

    def _save(self) -> None:
        from accounts.models import Membership
        from audit.service import record
        from workflows.models import Workflow
        from workflows.service import create_version

        session = self.session
        if len(self.steps) < 2:
            raise AuthorFailed(
                "nothing_done", "The agent didn't do anything after opening the page."
            )
        spec = self._spec()
        result = validate_spec(spec)
        if not result.ok:
            problems = "; ".join(f"{i.path}: {i.message}" for i in result.errors[:3])
            raise AuthorFailed("invalid_spec", f"The built workflow has errors: {problems}")
        actor = f"user:{session.user_id}"
        warnings = [f"{i.path}: {i.message}" for i in result.warnings]
        if session.base_version_id:
            workflow = session.base_version.workflow
            owner = Membership.objects.filter(
                org=session.org, user_id=session.user_id, role="owner"
            ).exists()
            version = create_version(
                workflow, spec, created_by=actor, sop_markdown=render_basic_sop(spec), warnings=warnings,
                parent=session.base_version, change_note=f"Rebuilt from instructions ({session.id[-6:]})",
                activate=owner,
            )  # fmt: skip
            if not owner:
                self.note = (
                    self.note + " " if self.note else ""
                ) + "Saved as a draft: a workspace owner activates it."
        else:
            workflow = Workflow.objects.create(
                org=session.org,
                name=spec["name"],
                description=spec["description"],
                created_by=session.user,
            )
            version = create_version(
                workflow, spec, created_by=actor, sop_markdown=render_basic_sop(spec), warnings=warnings,
                change_note="Built from instructions", activate=True,
            )  # fmt: skip
        record(
            "workflow.version.created", org=session.org, entity=version, actor=actor,
            metadata={"version": version.version, "activated": workflow.active_version_id == version.id, "source": "authoring"},
        )  # fmt: skip
        session.workflow, session.version = workflow, version
        session.save(update_fields=["workflow", "version", "updated_at"])

    def _finish(self, status: str, code: str, message: str) -> None:
        from audit.service import record

        session = self.session
        session.status = status
        session.error_code = code if status != "succeeded" else ""
        session.error_message = message if status != "succeeded" else self.note
        session.llm_cost_usd = self.cost
        session.question = {}
        session.finished_at = timezone.now()
        session.save()
        self.live.clear(session.id)
        record(
            f"authoring.{status}", org=session.org, entity=session, actor="system:author",
            metadata={"error_code": code} if code and status != "succeeded" else {},
        )  # fmt: skip
        self.publish({
            "type": "done", "status": status, "error": session.error_message, "error_code": session.error_code,
            "workflow_id": session.workflow_id or "", "version": session.version.version if session.version_id else None,
        })  # fmt: skip
        log.info("authoring %s finished: %s %s", session.id, status, code)
