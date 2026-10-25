"""The runner against a real browser and a local test app (skipped if Chromium is missing)."""

import copy
import json
import os
from typing import Any

import pytest
from django import db

from engine.runner.executor import Executor
from engine.spec.validate import validate_spec
from runs.models import CheckpointDecision, Run, RunStep
from secrets_vault.models import Secret
from workflows.models import Workflow
from workflows.service import create_version

from .site import Site

pytestmark = [pytest.mark.django_db, pytest.mark.browser]


@pytest.fixture(scope="module")
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")  # as engine/runner/browser.py
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - environment without browsers
            pytest.skip(f"Chromium not installed: {exc}")
        yield b
        b.close()
        # Inside Playwright's context Django uses its own connection; close that one.
        db.connections.close_all()


@pytest.fixture(scope="module")
def site():
    with Site() as s:
        yield s


class FakeLive:
    """In-memory stand-in for runs.live: records events, answers checkpoints."""

    def __init__(self, decisions: list[str | None] | None = None, cancel: bool = False) -> None:
        self.events: list[dict[str, Any]] = []
        self.decisions = list(decisions or [])
        self.cancel = cancel

    def publish(self, run_id: str, event: dict[str, Any]) -> None:
        self.events.append(event)

    def wait_for_decision(self, run_id: str, timeout_s: int) -> str | None:
        return self.decisions.pop(0) if self.decisions else None

    def cancel_requested(self, run_id: str) -> bool:
        return self.cancel

    def clear(self, run_id: str) -> None:
        pass

    def of(self, kind: str) -> list[dict[str, Any]]:
        return [e for e in self.events if e["type"] == kind]


def spec_for(host: str) -> dict[str, Any]:
    base = f"http://{host}"
    return {
        "spec_version": "1.0",
        "name": "Create invoice",
        "allowed_domains": [host],
        "start_url": f"{base}/login",
        "inputs": [
            {"name": "vendor_name", "type": "string", "required": True},
            {"name": "amount", "type": "number", "required": True},
            {"name": "due_date", "type": "date", "required": True},
        ],
        "secrets": [{"name": "app_login", "fields": ["username", "password"]}],
        "outputs": [{"name": "invoice_number", "type": "string"}],
        "steps": [
            {"id": "s1", "action": "navigate", "intent": "Open login", "url": f"{base}/login"},
            {
                "id": "s2",
                "action": "fill",
                "intent": "Username",
                "value": "{{secrets.app_login.username}}",
                "target": {"locators": [{"kind": "label", "value": "Username", "exact": True}]},
            },
            {
                "id": "s3",
                "action": "fill",
                "intent": "Password",
                "value": "{{secrets.app_login.password}}",
                "target": {"locators": [{"kind": "label", "value": "Password", "exact": True}]},
            },
            {
                "id": "s4",
                "action": "click",
                "intent": "Sign in",
                "target": {
                    "locators": [
                        {"kind": "role", "role": "button", "name": "Sign in", "exact": True}
                    ]
                },
                "assert_after": {"type": "url_matches", "value": "/form"},
            },
            {
                "id": "s5",
                "action": "select",
                "intent": "Choose the vendor",
                "label": "{{vendor_name}}",
                "target": {
                    "locators": [
                        {"kind": "role", "role": "combobox", "name": "Vendor", "exact": True}
                    ]
                },
            },
            {
                "id": "s6",
                "action": "select",
                "intent": "Set status",
                "label": "On hold",
                "target": {"locators": [{"kind": "label", "value": "Status", "exact": True}]},
            },
            {
                "id": "s7",
                "action": "fill",
                "intent": "Amount",
                "value": "{{amount | number:2}}",
                # A stale primary locator: the fallback (L1) finds it.
                "target": {
                    "locators": [
                        {"kind": "css", "value": "#amount-old"},
                        {"kind": "label", "value": "Amount", "exact": True},
                    ]
                },
            },
            {
                "id": "s8",
                "action": "fill",
                "intent": "Due date",
                "value": '{{due_date | date:"MM/DD/YYYY"}}',
                "target": {
                    "locators": [{"kind": "placeholder", "value": "MM/DD/YYYY", "exact": True}]
                },
            },
            {
                "id": "s9",
                "action": "check",
                "intent": "Mark urgent",
                "target": {"locators": [{"kind": "label", "value": "Urgent", "exact": True}]},
            },
            {
                "id": "s10",
                "action": "click",
                "intent": "Submit the invoice",
                "target": {
                    "locators": [
                        {"kind": "role", "role": "button", "name": "Submit", "exact": True}
                    ]
                },
                "checkpoint": {"type": "approval", "reason": "Creates an invoice"},
                "assert_after": {"type": "text_visible", "value": "Invoice created"},
            },
            {
                "id": "s11",
                "action": "extract",
                "intent": "Read the number",
                "output": "invoice_number",
                "pattern": r"INV-\d+",
                "target": {"locators": [{"kind": "css", "value": "body"}]},
            },
        ],  # fmt: skip
        "settings": {"default_timeout_ms": 4000},
    }


def make_run(account, spec: dict[str, Any], inputs: dict[str, Any] | None = None) -> Run:
    assert validate_spec(spec).ok, validate_spec(spec).errors
    workflow = Workflow.objects.create(org=account.org, name=spec["name"])
    version = create_version(workflow, spec, created_by="test", activate=True)
    if not Secret.objects.filter(org=account.org, name="app_login").exists():
        secret = Secret(org=account.org, name="app_login")
        secret.set_values({"username": "sara", "password": "hunter2-secret"})
        secret.save()
    return Run.objects.create(
        org=account.org,
        workflow=workflow,
        version=version,
        user=account.user,
        triggered_by="test",
        status=Run.Status.RUNNING,
        inputs=inputs
        or {"vendor_name": "City Power & Light", "amount": 1250.5, "due_date": "2026-11-05"},
    )


def test_full_run_with_approved_checkpoint(make_account, browser, site) -> None:
    run = make_run(make_account("sara@acme.test"), spec_for(site.host))
    live = FakeLive(decisions=["approve"])
    Executor(run, browser, live=live).execute()

    run.refresh_from_db()
    assert run.status == "succeeded", run.error_message
    assert run.outputs == {"invoice_number": "INV-48213"}
    steps = list(RunStep.objects.filter(run=run).values_list("step_id", "status", "rung"))
    assert [s[1] for s in steps] == ["ok"] * 11
    assert dict((s[0], s[2]) for s in steps)["s7"] == "L1"  # primary css was stale
    assert dict((s[0], s[2]) for s in steps)["s2"] == "L0"

    checkpoint = live.of("checkpoint")[0]
    assert checkpoint["step_id"] == "s10" and checkpoint["reason"] == "Creates an invoice"
    assert live.of("done")[-1]["status"] == "succeeded"
    assert len(live.of("frame")) >= 11
    assert "hunter2-secret" not in json.dumps(live.events)


def test_values_reach_the_page_formatted(make_account, browser, site) -> None:
    spec = spec_for(site.host)
    spec["outputs"].append({"name": "echo", "type": "string"})
    spec["steps"].append(
        {"id": "s12", "action": "extract", "intent": "Echo", "output": "echo",
         "target": {"locators": [{"kind": "css", "value": "#echo"}]}}
    )  # fmt: skip
    run = make_run(make_account("sara@acme.test"), spec)
    Executor(run, browser, live=FakeLive(decisions=["approve"])).execute()
    run.refresh_from_db()
    echo = dict(line.split("=", 1) for line in run.outputs["echo"].splitlines())
    assert echo == {
        "amount": "1250.50",
        "due": "11/05/2026",
        "status": "h",
        "urgent": "true",
        "vendor": "City Power & Light",
    }


def test_rejected_checkpoint_stops_before_the_click(make_account, browser, site) -> None:
    run = make_run(make_account("sara@acme.test"), spec_for(site.host))
    Executor(run, browser, live=FakeLive(decisions=["reject"])).execute()
    run.refresh_from_db()
    assert run.status == "rejected"
    assert run.outputs == {}
    last = RunStep.objects.filter(run=run).order_by("-seq").first()
    assert last is not None
    assert last.step_id == "s10" and last.status == "skipped"


def test_missing_element_fails_with_a_clear_error(make_account, browser, site) -> None:
    spec = spec_for(site.host)
    spec["steps"][3]["target"]["locators"] = [
        {"kind": "role", "role": "button", "name": "Log in", "exact": True}
    ]
    run = make_run(make_account("sara@acme.test"), spec)
    Executor(run, browser, live=FakeLive()).execute()
    run.refresh_from_db()
    assert run.status == "failed" and run.error_code == "element_not_found"
    assert "s4" in run.error_message
    assert RunStep.objects.get(run=run, step_id="s4").status == "failed"


def test_navigation_outside_allowed_sites_is_blocked(make_account, browser, site) -> None:
    spec = copy.deepcopy(spec_for(site.host))
    spec["steps"] = spec["steps"][:1]
    spec["outputs"] = []
    run = make_run(make_account("sara@acme.test"), spec)
    run.version.spec["steps"][0]["url"] = "http://evil.example.test/login"  # bypassing validation
    Executor(run, browser, live=FakeLive()).execute()
    run.refresh_from_db()
    assert run.status == "failed" and run.error_code == "domain_blocked"


def test_cancel_and_timeouts(make_account, browser, site) -> None:
    account = make_account("sara@acme.test")
    run = make_run(account, spec_for(site.host))
    Executor(run, browser, live=FakeLive(cancel=True)).execute()
    run.refresh_from_db()
    assert run.status == "cancelled"
    assert RunStep.objects.filter(run=run).count() == 0

    run = make_run(account, spec_for(site.host))
    Executor(run, browser, live=FakeLive(decisions=[None])).execute()  # nobody answered
    run.refresh_from_db()
    assert run.status == "timed_out"
    assert CheckpointDecision.objects.count() == 0


def test_secrets_are_scrubbed_from_errors(make_account, browser, site) -> None:
    spec = spec_for(site.host)
    spec["steps"][2]["target"]["locators"] = [{"kind": "css", "value": "#nope"}]
    spec["steps"][2]["intent"] = "Type hunter2-secret"  # contrived: a secret in the message
    run = make_run(make_account("sara@acme.test"), spec)
    Executor(run, browser, live=FakeLive()).execute()
    run.refresh_from_db()
    assert run.status == "failed"
    assert "hunter2-secret" not in run.error_message
    assert "•••" in run.error_message
