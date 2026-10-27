"""The authoring agent against a real browser and the runner's local test app (skipped if
Chromium is missing). The fake provider follows the plain instructions mechanically."""

import json
from typing import Any

import pytest

from authoring.models import AuthoringSession
from engine.author.agent import Author
from engine.llm.fake import FakeProvider
from engine.llm.fake_author import _action
from engine.runner.executor import Executor
from engine.runner.tests.test_executor import FakeLive, browser, site  # noqa: F401 - fixtures
from engine.spec.validate import validate_spec
from runs.models import Run
from secrets_vault.models import Secret
from workflows.models import Workflow, WorkflowVersion

pytestmark = [pytest.mark.django_db, pytest.mark.browser]


def instructions(host: str, *, login: str = "Type sara in Username") -> str:
    return f"""Go to http://{host}/login
{login}
Click Sign in
Select Northwind Ltd in Vendor
Type 1250.50 in Amount
Type 11/15/2026 in Due date
Click Submit
Wait for Invoice created
Read Invoice number as invoice_number"""


class Recording(FakeProvider):
    """The fake provider, keeping every request it was sent."""

    def __init__(self) -> None:
        self.requests: list[Any] = []

    def author(self, req):
        self.requests.append(req)
        return super().author(req)


class Scripted(FakeProvider):
    """Always answers the same action (to test what the agent refuses)."""

    def __init__(self, **fields: Any) -> None:
        self.answer = _action(**fields)

    def author(self, req):
        return self.answer, super().author(req)[1]


def build(account, host: str, text: str, *, live: FakeLive, provider=None) -> AuthoringSession:
    session = AuthoringSession.objects.create(
        org=account.org, user=account.user, start_url=f"http://{host}/login", instructions=text,
        status=AuthoringSession.Status.RUNNING,
    )  # fmt: skip
    Author(session, browser_ref[0], live=live, provider=provider or FakeProvider()).execute()
    session.refresh_from_db()
    return session


browser_ref: list[Any] = []


@pytest.fixture(autouse=True)
def _browser(browser):  # noqa: F811 - the imported fixture
    browser_ref[:] = [browser]
    yield


def saved(session: AuthoringSession) -> tuple[Workflow, WorkflowVersion]:
    assert session.workflow is not None and session.version is not None, session.error_message
    return session.workflow, session.version


def replay(account, session: AuthoringSession) -> Run:
    workflow, version = saved(session)
    inputs = {i["name"]: i["example"] for i in version.spec["inputs"]}
    run = Run.objects.create(
        org=account.org, workflow=workflow, version=version, user=account.user,
        triggered_by="test", inputs=inputs, status=Run.Status.RUNNING,
    )  # fmt: skip
    Executor(run, browser_ref[0], live=FakeLive(decisions=["approve"])).execute()
    run.refresh_from_db()
    return run


def test_builds_a_workflow_that_replays_without_ai(site, make_account):  # noqa: F811
    account = make_account("sara@acme.test")
    live = FakeLive(decisions=["approve"])  # the Submit step asks first
    session = build(account, site.host, instructions(site.host), live=live)

    assert session.status == "succeeded", session.error_message
    spec = saved(session)[1].spec
    assert validate_spec(spec).ok
    actions = [s["action"] for s in spec["steps"]]
    assert actions == [
        "navigate",
        "fill",
        "click",
        "select",
        "fill",
        "fill",
        "click",
        "wait_for",
        "extract",
    ]
    submit = spec["steps"][6]
    assert submit["checkpoint"]["type"] == "approval"  # risky: asks on every run too
    assert {i["name"] for i in spec["inputs"]} >= {"amount", "due_date", "vendor"}
    assert spec["outputs"] == [
        {"name": "invoice_number", "type": "string", "description": "Read the Invoice number"}
    ]
    assert saved(session)[0].active_version_id == session.version_id
    assert [e["type"] for e in live.of("checkpoint")] == ["checkpoint"]
    assert all(e["status"] in ("ok", "running", "awaiting_approval") for e in live.of("agent_step"))

    run = replay(account, session)
    assert run.status == "succeeded", run.error_message
    assert run.outputs["invoice_number"] == "INV-48213"


def test_a_declined_risky_step_is_kept_but_not_done(site, make_account):  # noqa: F811
    account = make_account("sara@acme.test")
    session = build(
        account, site.host, instructions(site.host), live=FakeLive(decisions=["reject"])
    )

    assert session.status == "succeeded"
    assert "wasn't done" in session.error_message
    steps = saved(session)[1].spec["steps"]
    assert steps[-1]["intent"] == "Click Submit" and steps[-1]["checkpoint"]["type"] == "approval"
    assert session.steps[-1]["status"] == "skipped"


def test_saved_login_values_never_reach_the_ai(site, make_account):  # noqa: F811
    account = make_account("sara@acme.test")
    secret = Secret(org=account.org, name="site_login")
    test_password = "pw-Hunter2-x"  # gitleaks:allow (test value)
    secret.set_values({"username": "sara-secret-user", "password": test_password})
    secret.save()
    provider = Recording()
    text = instructions(site.host, login="Log in with my saved login site_login").replace(
        "Click Sign in\n", ""
    )
    session = build(
        account, site.host, text, live=FakeLive(decisions=["approve"]), provider=provider
    )

    assert session.status == "succeeded", session.error_message
    fills = [s for s in saved(session)[1].spec["steps"] if s["action"] == "fill"][:2]
    assert [f["value"] for f in fills] == [
        "{{secrets.site_login.username}}",
        "{{secrets.site_login.password}}",
    ]
    sent = json.dumps([r.__dict__ for r in provider.requests], default=str)
    stored = json.dumps(session.steps)
    for value in ("sara-secret-user", "pw-Hunter2-x"):
        assert value not in sent and value not in stored
    assert replay(account, session).status == "succeeded"


def test_an_element_that_is_not_on_the_page_is_refused(site, make_account):  # noqa: F811
    account = make_account("sara@acme.test")
    provider = Scripted(action="click", candidate_id="e999", intent="Click Delete all records")
    session = build(account, site.host, "Click Sign in", live=FakeLive(), provider=provider)

    assert session.status == "failed" and session.error_code == "agent_failed"
    assert "no element 'e999'" in session.error_message
    assert session.workflow_id is None


def test_it_only_goes_to_sites_named_in_the_instructions(site, make_account):  # noqa: F811
    account = make_account("sara@acme.test")
    provider = Scripted(action="navigate", url="http://evil.example/steal", intent="Open a page")
    session = build(account, site.host, "Click Sign in", live=FakeLive(), provider=provider)

    assert session.status == "failed"
    assert "evil.example isn't one of the sites" in session.error_message


class BusyOnce(FakeProvider):
    """Rate limited on the first call, then fine."""

    def __init__(self) -> None:
        self.calls = 0

    def author(self, req):
        from engine.llm import LLMError

        self.calls += 1
        if self.calls == 1:
            raise LLMError("llm_unavailable", "Rate limit reached.", retryable=True)
        return super().author(req)


def test_a_busy_ai_is_retried(site, make_account, monkeypatch):  # noqa: F811
    monkeypatch.setattr("engine.author.agent.RETRY_PAUSES_S", (0, 0, 0))
    account = make_account("sara@acme.test")
    live = FakeLive(decisions=["approve"])
    session = build(account, site.host, instructions(site.host), live=live, provider=BusyOnce())

    assert session.status == "succeeded", session.error_message
    assert any("Trying again" in (e.get("message") or "") for e in live.of("thinking"))
