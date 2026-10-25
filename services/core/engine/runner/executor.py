"""Execute one run: a pinned workflow version with given inputs (docs/08).

Per step: locate (L0 primary, L1 fallbacks) → checkpoint? → act → post-condition →
screenshot + live events. Self-healing (L2/L3) plugs into ``_find`` on Day 10.
Secret values are resolved here, used in the browser only, and scrubbed from any message
that leaves this module.
"""

import base64
import contextlib
import fnmatch
import logging
import re
import time
from typing import Any
from urllib.parse import urlsplit

from django.conf import settings
from django.utils import timezone
from playwright.sync_api import Browser, BrowserContext, Page, Route
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from common.storage import get_storage
from engine.spec.templating import TemplateError, render
from engine.spec.validate import host_allowed

from .locate import ElementNotFound, Found, find

log = logging.getLogger(__name__)

SETTLE_MS = 2000  # wait for the page to calm down after an action without an assertion
HIGHLIGHT = "3px solid #f59e0b"


class RunFailed(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class RunStopped(Exception):
    """Ended by a person or a limit: rejected, cancelled, timed out."""

    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class Executor:
    def __init__(self, run, browser: Browser, *, live=None) -> None:
        from runs import live as default_live

        self.run = run
        self.browser = browser
        self.live = live or default_live
        self.spec: dict[str, Any] = run.version.spec
        self.steps: list[dict[str, Any]] = self.spec["steps"]
        self.allowed: list[str] = [
            *self.spec["allowed_domains"],
            *settings.RUNNER_EXTRA_ALLOWED_HOSTS,
        ]
        self.default_timeout: int = self.spec.get("settings", {}).get("default_timeout_ms", 15000)
        self.outputs: dict[str, Any] = {}
        self.secrets: dict[str, dict[str, str]] = {}
        self.blocked: list[str] = []
        self.started = time.monotonic()
        self.waited = 0.0  # time spent waiting for people, not counted against the limit
        self.seq = 0
        self.heals: list = []  # healer.Heal, one per step found again after a page change

    # --- events -------------------------------------------------------------------------

    def publish(self, event: dict[str, Any]) -> None:
        try:
            self.live.publish(self.run.id, event)
        except Exception:  # live view is best effort; never fail a run over it
            log.warning("run %s: couldn't publish %s", self.run.id, event.get("type"))

    def scrub(self, text: str) -> str:
        for values in self.secrets.values():
            for value in values.values():
                if value and len(value) >= 3:
                    text = text.replace(value, "•••")
        return text[:2000]

    # --- entry point --------------------------------------------------------------------

    def execute(self) -> None:
        from runs.models import Run

        run = self.run
        status: str = Run.Status.SUCCEEDED
        code, message = "", ""
        context: BrowserContext | None = None
        try:
            self.secrets = self._load_secrets()
            context = self._new_context()
            page = context.new_page()
            for step in self.steps:
                self._check_limits()
                self._run_step(page, step)
        except RunStopped as stop:
            status, code, message = stop.status, stop.status, stop.message
        except RunFailed as failure:
            status, code, message = Run.Status.FAILED, failure.code, self.scrub(failure.message)
        except Exception as exc:  # a bug or a browser crash: fail the run, keep the worker
            log.exception("run %s crashed", run.id)
            status, code, message = Run.Status.FAILED, "internal_error", self.scrub(str(exc))
        finally:
            if context is not None:
                with contextlib.suppress(PlaywrightError):
                    context.close()
        self._finish(status, code, message)

    # --- setup --------------------------------------------------------------------------

    def _load_secrets(self) -> dict[str, dict[str, str]]:
        from secrets_vault.models import Secret

        names = [s["name"] for s in self.spec.get("secrets", [])]
        found = {
            s.name: s.values() for s in Secret.objects.for_org(self.run.org).filter(name__in=names)
        }
        missing = [n for n in names if n not in found]
        if missing:
            raise RunFailed("missing_secrets", f"Saved login(s) not found: {', '.join(missing)}.")
        return found

    def _new_context(self) -> BrowserContext:
        context = self.browser.new_context(
            viewport={"width": 1280, "height": 800},
            accept_downloads=False,
            permissions=[],
            locale="en-US",
        )
        context.set_default_timeout(self.default_timeout)
        context.route("**/*", self._guard)
        return context

    def _guard(self, route: Route) -> None:
        """Only the workflow's own sites may be contacted (navigations and requests)."""
        url = urlsplit(route.request.url)
        if url.scheme not in ("http", "https") or host_allowed(url.netloc, self.allowed):
            route.continue_()
            return
        self.blocked.append(url.netloc)
        route.abort("blockedbyclient")

    def _check_limits(self) -> None:
        if self.live.cancel_requested(self.run.id):
            raise RunStopped("cancelled", "Cancelled by a user.")
        busy = time.monotonic() - self.started - self.waited
        if busy > settings.RUN_MAX_SECONDS:
            raise RunStopped(
                "timed_out", f"The run took longer than {settings.RUN_MAX_SECONDS // 60} minutes."
            )

    # --- steps --------------------------------------------------------------------------

    def _run_step(self, page: Page, step: dict[str, Any]) -> None:
        from runs.models import Run, RunStep

        self.seq += 1
        run = self.run
        run.current_step_id = step["id"]
        run.save(update_fields=["current_step_id", "updated_at"])
        record = RunStep.objects.create(
            org_id=run.org_id, run=run, step_id=step["id"], seq=self.seq, started_at=timezone.now()
        )
        self.publish({"type": "step", "step_id": step["id"], "status": "running"})
        timeout = step.get("timeout_ms") or self.default_timeout
        try:
            found = self._find(page, step, timeout) if step.get("target") else None
            if found is not None:
                record.locator_used, record.rung = found.spec, found.rung
            if (step.get("checkpoint") or {}).get("type") == "approval":
                self._checkpoint(page, step, record, found)
            self._act(page, step, found, timeout)
            self._post_condition(page, step, timeout)
        except (RunFailed, RunStopped) as exc:
            if isinstance(exc, RunFailed) and record.rung in ("L2", "L3"):
                from .healer import discard_last

                discard_last(
                    self, step["id"], "the page didn't react the way it did when recorded."
                )
            record.status = (
                RunStep.Status.FAILED if isinstance(exc, RunFailed) else RunStep.Status.SKIPPED
            )
            record.error = self.scrub(exc.message)
            raise
        finally:
            if record.status in (RunStep.Status.RUNNING, RunStep.Status.AWAITING_APPROVAL):
                healed = record.rung in ("L2", "L3")
                record.status = RunStep.Status.HEALED if healed else RunStep.Status.OK
            record.finished_at = timezone.now()
            # After the action (the approval screenshot is kept on the checkpoint decision).
            record.screenshot_ref = self._screenshot(
                page, f"{self.seq:03d}-{step['id']}.jpg", step["id"]
            )
            record.save()
            self.publish(
                {
                    "type": "step",
                    "step_id": step["id"],
                    "status": record.status,
                    "rung": record.rung,
                    "error": record.error,
                    "screenshot_ref": record.screenshot_ref,
                }
            )
        if run.status != Run.Status.RUNNING:
            run.status = Run.Status.RUNNING
            run.save(update_fields=["status", "updated_at"])

    def _find(self, page: Page, step: dict[str, Any], timeout: int) -> Found:
        from .healer import HealFailed, fallback_ok, heal

        try:
            found = find(page, step["target"]["locators"], timeout)
            if fallback_ok(found, step["target"].get("fingerprint")):
                return found
            not_found = ElementNotFound(step["target"]["locators"], [])
            not_found.args = (
                "Only a text or position-based locator matched, and that element doesn't look like the recorded one.",
            )
        except ElementNotFound as exc:
            not_found = exc
        try:  # L2 fingerprint match, then L3 AI repair
            return heal(self, page, step)
        except HealFailed as failed:
            raise RunFailed(
                failed.code,
                f"Step {step['id']} ({step['intent']}): {not_found} Self-healing: {failed.message}.",
            ) from None

    def _value(self, template: str) -> str:
        try:
            return render(template, self.run.inputs, self.secrets, self.outputs)
        except TemplateError as exc:
            raise RunFailed("template_error", str(exc)) from None

    def _act(self, page: Page, step: dict[str, Any], found: Found | None, timeout: int) -> None:
        action = step["action"]
        try:
            if action == "navigate":
                url = self._value(step["url"])
                if not host_allowed(urlsplit(url).netloc, self.allowed):
                    raise RunFailed(
                        "domain_blocked", f"{urlsplit(url).netloc} isn't in the allowed sites."
                    )
                page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            elif found is None and action not in ("press", "wait_for", "assert"):
                raise RunFailed("invalid_step", f"Step {step['id']} has no target.")
            elif action == "click":
                found.locator.click(timeout=timeout)  # type: ignore[union-attr]
            elif action == "fill":
                found.locator.fill(self._value(step["value"]), timeout=timeout)  # type: ignore[union-attr]
            elif action == "select":
                self._select(page, step, found, timeout)  # type: ignore[arg-type]
            elif action == "check":
                found.locator.check(timeout=timeout)  # type: ignore[union-attr]
            elif action == "uncheck":
                found.locator.uncheck(timeout=timeout)  # type: ignore[union-attr]
            elif action == "press":
                if found is not None:
                    found.locator.press(step["key"], timeout=timeout)
                else:
                    page.keyboard.press(step["key"])
            elif action in ("wait_for", "assert"):
                if not self._condition(page, step["condition"], timeout):
                    code = "assertion_failed" if action == "assert" else "wait_timed_out"
                    raise RunFailed(
                        code, f"Step {step['id']} ({step['intent']}): condition not met."
                    )
            elif action == "extract":
                self._extract(step, found)  # type: ignore[arg-type]
            else:
                raise RunFailed("invalid_step", f"Unknown action {action!r}.")
        except PlaywrightTimeout:
            if self.blocked:
                raise RunFailed(
                    "domain_blocked",
                    f"The page tried to reach a site outside the workflow: {self.blocked[-1]}.",
                ) from None
            raise RunFailed(
                "action_timed_out", f"Step {step['id']} ({step['intent']}) didn't complete in time."
            ) from None
        except PlaywrightError as exc:
            message = str(exc).splitlines()[0]
            if "ERR_BLOCKED_BY_CLIENT" in message:
                raise RunFailed(
                    "domain_blocked", "Navigation to a site outside the workflow was blocked."
                ) from None
            raise RunFailed(
                "action_failed", f"Step {step['id']} ({step['intent']}): {message}"
            ) from None

    def _select(self, page: Page, step: dict[str, Any], found: Found, timeout: int) -> None:
        label = self._value(step["label"]) if "label" in step else None
        value = self._value(step["value"]) if "value" in step else None
        if found.locator.evaluate("e => e.tagName") == "SELECT":
            if label is not None:
                found.locator.select_option(label=label, timeout=timeout)
            else:
                found.locator.select_option(value=value, timeout=timeout)
            return
        # Custom dropdown: open it, then pick the option by its visible name.
        found.locator.click(timeout=timeout)
        wanted = label if label is not None else value or ""
        option_locators = [
            {"kind": "role", "role": "option", "name": wanted, "exact": True},
            {"kind": "role", "role": "menuitem", "name": wanted, "exact": True},
            {"kind": "text", "value": wanted, "exact": True},
        ]
        try:
            option = find(page, option_locators, timeout)
        except ElementNotFound:
            raise RunFailed(
                "option_not_found", f'Step {step["id"]}: no option "{wanted}" to choose.'
            ) from None
        option.locator.click(timeout=timeout)

    def _extract(self, step: dict[str, Any], found: Found) -> None:
        text = (
            found.locator.inner_text()
            if step.get("attribute", "text") == "text"
            else (found.locator.get_attribute(step["attribute"]) or "")
        )
        value: Any = text.strip()
        if step.get("pattern"):
            match = re.search(step["pattern"], text)
            if match is None:
                raise RunFailed(
                    "extract_failed", f"Step {step['id']}: nothing matched {step['pattern']}."
                )
            value = match.group(0)
        out = next((o for o in self.spec.get("outputs", []) if o["name"] == step["output"]), None)
        if out is not None and out.get("type") == "number":
            try:
                value = float(str(value).replace(",", ""))
            except ValueError:
                raise RunFailed(
                    "extract_failed", f"Step {step['id']}: {value!r} isn't a number."
                ) from None
        self.outputs[step["output"]] = value

    def _condition(self, page: Page, cond: dict[str, Any], timeout: int) -> bool:
        kind = cond["type"]
        deadline = time.monotonic() + timeout / 1000
        try:
            if kind == "url_matches":
                pattern = cond["value"]
                while True:
                    url = page.url
                    target = url if pattern.startswith("http") else urlsplit(url).path
                    if fnmatch.fnmatchcase(target, pattern):
                        return True
                    if time.monotonic() >= deadline:
                        return False
                    # Not time.sleep: Playwright only records in-app URL changes
                    # (pushState after a sign-in, SPA links) while it is waiting itself.
                    page.wait_for_timeout(200)
            if kind == "text_visible":
                text = self._value(cond["value"])
                page.get_by_text(text).first.wait_for(state="visible", timeout=timeout)
                return True
            if kind == "element_visible":
                find(page, cond["target"]["locators"], timeout)
                return True
            if kind == "network_idle":
                page.wait_for_load_state("networkidle", timeout=timeout)
                return True
        except (PlaywrightTimeout, ElementNotFound):
            return False
        return False

    def _post_condition(self, page: Page, step: dict[str, Any], timeout: int) -> None:
        cond = step.get("assert_after")
        if cond:
            if not self._condition(page, cond, timeout):
                raise RunFailed(
                    "assertion_failed",
                    f"Step {step['id']} ({step['intent']}): expected {cond['type'].replace('_', ' ')} "
                    f"“{cond.get('value', '')}” afterwards.",
                )
            return
        if step["action"] in ("extract", "wait_for", "assert"):
            return
        try:  # let navigations and re-renders settle; not an error if the page keeps busy
            page.wait_for_load_state("load", timeout=SETTLE_MS * 2)
            page.wait_for_load_state("networkidle", timeout=SETTLE_MS)
        except PlaywrightTimeout:
            pass

    # --- checkpoints --------------------------------------------------------------------

    def _checkpoint(self, page: Page, step: dict[str, Any], record, found: Found | None) -> None:
        from runs.models import Run, RunStep

        reason = step["checkpoint"].get("reason") or "This step needs approval."
        if found is not None:  # show exactly what will be clicked
            with contextlib.suppress(PlaywrightError):
                found.locator.evaluate(
                    f"e => {{ e.dataset.woOutline = e.style.outline; e.style.outline = '{HIGHLIGHT}'; e.scrollIntoView({{block: 'center'}}); }}"
                )
        record.screenshot_ref = self._screenshot(
            page, f"{self.seq:03d}-{step['id']}-approval.jpg", step["id"]
        )
        record.status = RunStep.Status.AWAITING_APPROVAL
        record.save(
            update_fields=["screenshot_ref", "status", "locator_used", "rung", "updated_at"]
        )
        Run.objects.filter(pk=self.run.pk).update(
            status=Run.Status.AWAITING_APPROVAL,
            current_step_id=step["id"],
            updated_at=timezone.now(),
        )
        self.run.status = Run.Status.AWAITING_APPROVAL
        self.publish(
            {
                "type": "checkpoint",
                "heal": next((h.explanation for h in self.heals if h.step_id == step["id"]), None),
                "step_id": step["id"],
                "intent": step["intent"],
                "reason": reason,
                "screenshot_ref": record.screenshot_ref,
            }
        )
        log.info("run %s waiting for approval at %s", self.run.id, step["id"])
        self._batch_approval()
        began = time.monotonic()
        decision = self.live.wait_for_decision(self.run.id, settings.RUN_CHECKPOINT_TIMEOUT_S)
        self.waited += time.monotonic() - began
        self.run.refresh_from_db(fields=["status"])
        if found is not None:
            with contextlib.suppress(PlaywrightError):
                found.locator.evaluate(
                    "e => { e.style.outline = e.dataset.woOutline || ''; delete e.dataset.woOutline; }"
                )
        if decision is None:
            raise RunStopped("timed_out", f"Nobody approved step {step['id']} in time.")
        if decision == "cancel":
            raise RunStopped("cancelled", "Cancelled by a user.")
        if decision == "reject":
            raise RunStopped("rejected", f"Step {step['id']} was rejected.")
        self.publish({"type": "approved", "step_id": step["id"]})

    def _batch_approval(self) -> None:
        """In a batch an owner may have approved every checkpoint at once: answer this one
        the same way (recorded as a checkpoint decision, like a click on Approve)."""
        from runs.models import Batch
        from runs.service import approve_waiting_run

        if not self.run.batch_id:
            return
        batch = Batch.objects.filter(pk=self.run.batch_id, approve_all=True).first()
        if batch is not None:
            approve_waiting_run(self.run, batch.approved_by, "Approved for the whole batch")

    # --- artifacts ----------------------------------------------------------------------

    def _screenshot(self, page: Page, name: str, step_id: str) -> str:
        try:
            jpeg = page.screenshot(type="jpeg", quality=60, timeout=5000)
        except PlaywrightError:
            return ""
        try:
            get_storage().put_bytes(self.run.artifacts_prefix + name, jpeg, "image/jpeg")
        except Exception:
            log.warning("run %s: couldn't store %s", self.run.id, name)
            name = ""
        self.publish(
            {"type": "frame", "step_id": step_id, "jpeg_b64": base64.b64encode(jpeg).decode()}
        )
        return name

    # --- end ----------------------------------------------------------------------------

    def _finish(self, status: str, code: str, message: str) -> None:
        from audit.service import record

        run = self.run
        run.status = status
        run.error_code = code if status != "succeeded" else ""
        run.error_message = message
        run.outputs = self.outputs
        run.finished_at = timezone.now()
        if status == "succeeded":
            run.current_step_id = ""
        run.save()
        self.live.clear(run.id)
        if self.heals:
            from .healer import persist

            try:
                persist(self)
            except Exception:
                log.exception("run %s: couldn't save the healed version", run.id)
        record(
            f"run.{status}",
            org=run.org,
            entity=run,
            actor="system:runner",
            metadata={"error_code": run.error_code} if run.error_code else {},
        )
        self.publish(
            {
                "type": "done",
                "status": status,
                "outputs": self.outputs,
                "error": message,
                "error_code": run.error_code,
            }
        )
        log.info("run %s finished: %s %s", run.id, status, code)
