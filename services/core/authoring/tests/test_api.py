from typing import Any

import pytest

from authoring.models import AuthoringSession
from runs.models import Run
from workflows.models import Workflow
from workflows.service import create_version

pytestmark = pytest.mark.django_db

SPEC: dict[str, Any] = {
    "spec_version": "1.0",
    "name": "Search the bill",
    "allowed_domains": ["bill.example"],
    "start_url": "https://bill.example/search",
    "inputs": [{"name": "reference", "type": "string"}],
    "secrets": [],
    "outputs": [],
    "steps": [
        {"id": "s1", "action": "navigate", "intent": "Open the bill site", "url": "https://bill.example/search"},
        {"id": "s2", "action": "click", "intent": "Search for the bill",
         "target": {"locators": [{"kind": "role", "role": "button", "name": "Search", "exact": True}]}},
    ],
    "settings": {"default_timeout_ms": 15000},
}  # fmt: skip


def failed_run(account) -> Run:
    workflow = Workflow.objects.create(org=account.org, name=SPEC["name"])
    version = create_version(workflow, SPEC, created_by="test", activate=True)
    return Run.objects.create(
        org=account.org, workflow=workflow, version=version, user=account.user, triggered_by="test",
        inputs={"reference": "12345"}, status=Run.Status.FAILED, current_step_id="s2",
        error_code="element_not_found", error_message="Step s2: nothing matched.",
    )  # fmt: skip


def test_start_from_instructions(make_account):
    sara = make_account("sara@acme.test")
    r = sara.client.post(
        "/api/v1/authoring",
        {"start_url": "https://petxapp.com/login", "instructions": "Log in and open My Ads"},
        format="json",
    )
    assert r.status_code == 202, r.content
    assert r.data["status"] == "queued" and r.data["mode"] == "create"
    assert r.data["id"].startswith("aut_")
    assert sara.client.get(f"/api/v1/authoring/{r.data['id']}").status_code == 200


def test_start_needs_a_link(make_account):
    sara = make_account("sara@acme.test")
    r = sara.client.post("/api/v1/authoring", {"instructions": "Do it"}, format="json")
    assert r.status_code == 400
    r = sara.client.post(
        "/api/v1/authoring",
        {"start_url": "ftp://x.example", "instructions": "Do it"},
        format="json",
    )
    assert r.status_code == 400


def test_fix_a_failed_run(make_account):
    sara = make_account("sara@acme.test")
    run = failed_run(sara)
    r = sara.client.post(
        "/api/v1/authoring",
        {"run_id": run.id, "instructions": "The button is now called Find bill"},
        format="json",
    )
    assert r.status_code == 202, r.content
    session = AuthoringSession.objects.get(pk=r.data["id"])
    assert session.mode == "fix" and session.base_version_id == run.version_id
    assert session.start_url == SPEC["start_url"]
    text = session.instructions
    assert "1. Open the bill site" in text and "It failed at “Search for the bill”" in text
    assert "reference = 12345" in text and text.endswith("The button is now called Find bill")


def test_other_workspaces_cannot_see_or_fix(make_account):
    sara, omar = make_account("sara@acme.test"), make_account("omar@other.test")
    run = failed_run(sara)
    r = omar.client.post(
        "/api/v1/authoring", {"run_id": run.id, "instructions": "x"}, format="json"
    )
    assert r.status_code == 404
    session = AuthoringSession.objects.create(
        org=sara.org, user=sara.user, start_url="https://a.example", instructions="x"
    )
    assert omar.client.get(f"/api/v1/authoring/{session.id}").status_code == 404


def test_decisions_only_while_waiting(make_account):
    sara = make_account("sara@acme.test")
    session = AuthoringSession.objects.create(
        org=sara.org, user=sara.user, start_url="https://a.example", instructions="x"
    )
    url = f"/api/v1/authoring/{session.id}/decision"
    assert sara.client.post(url, {"decision": "approve"}, format="json").status_code == 409


def test_members_decide_only_on_their_own(make_account):
    sara = make_account("sara@acme.test")
    member = make_account("lee@acme.test", org=sara.org, role="member")
    session = AuthoringSession.objects.create(
        org=sara.org, user=sara.user, start_url="https://a.example", instructions="x",
        status=AuthoringSession.Status.AWAITING_APPROVAL,
    )  # fmt: skip
    url = f"/api/v1/authoring/{session.id}/decision"
    assert member.client.post(url, {"decision": "approve"}, format="json").status_code == 403


def test_cancel_before_it_starts(make_account):
    sara = make_account("sara@acme.test")
    session = AuthoringSession.objects.create(
        org=sara.org, user=sara.user, start_url="https://a.example", instructions="x"
    )
    r = sara.client.post(f"/api/v1/authoring/{session.id}/cancel")
    assert r.status_code == 200 and r.data["status"] == "cancelled"


def test_counts_against_the_hourly_ai_limit(make_account, settings):
    settings.ORG_COMPILES_PER_HOUR = 1
    sara = make_account("sara@acme.test")
    body = {"start_url": "https://a.example", "instructions": "x"}
    assert sara.client.post("/api/v1/authoring", body, format="json").status_code == 202
    r = sara.client.post("/api/v1/authoring", body, format="json")
    assert r.status_code == 429 and r.data["error"]["code"] == "rate_limited"
