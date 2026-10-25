import json

import pytest
from asgiref.sync import async_to_sync
from django.test import AsyncClient

from audit.models import AuditLog
from runs import live
from runs.models import CheckpointDecision, Run, RunStep
from secrets_vault.models import Secret
from workflows.models import Workflow
from workflows.service import create_version

pytestmark = pytest.mark.django_db

SPEC = {
    "spec_version": "1.0",
    "name": "Create invoice",
    "allowed_domains": ["acme.test"],
    "start_url": "https://acme.test/login",
    "inputs": [
        {"name": "vendor_name", "type": "string", "required": True},
        {"name": "amount", "type": "number", "required": True},
        {"name": "due_date", "type": "date", "required": True},
        {"name": "note", "type": "string", "required": False},
    ],
    "secrets": [{"name": "acme_login", "fields": ["username", "password"]}],
    "outputs": [],
    "steps": [
        {"id": "s1", "action": "navigate", "intent": "Open", "url": "https://acme.test/login"},
        {
            "id": "s2",
            "action": "fill",
            "intent": "Password",
            "value": "{{secrets.acme_login.password}}",
            "target": {"locators": [{"kind": "label", "value": "Password"}]},
        },
    ],  # fmt: skip
    "settings": {},
}
INPUTS = {"vendor_name": "Northwind", "amount": "1250.50", "due_date": "2026-11-15"}


@pytest.fixture
def enqueued(monkeypatch) -> list[str]:
    """Capture runs handed to the runner instead of launching a browser."""
    calls: list[str] = []
    monkeypatch.setattr("runs.views._enqueue_run", calls.append)
    return calls


@pytest.fixture
def setup(make_account):
    owner = make_account("sara@acme.test")
    workflow = Workflow.objects.create(org=owner.org, name="Create invoice")
    create_version(workflow, SPEC, created_by="test", activate=True)
    secret = Secret(org=owner.org, name="acme_login")
    secret.set_values({"username": "sara", "password": "acme-demo"})
    secret.save()
    return owner, workflow


def start(client, workflow, inputs=None, **extra):
    return client.post(
        f"/api/v1/workflows/{workflow.id}/runs",
        {"inputs": inputs or INPUTS, **extra},
        format="json",
    )


def test_start_validates_inputs_and_queues(
    setup, enqueued, django_capture_on_commit_callbacks
) -> None:
    owner, workflow = setup
    with django_capture_on_commit_callbacks(execute=True):
        response = start(owner.client, workflow)
    assert response.status_code == 202, response.content
    assert response.data["status"] == "queued" and response.data["version"] == 1
    assert response.data["inputs"] == {
        "vendor_name": "Northwind",
        "amount": 1250.5,
        "due_date": "2026-11-15",
    }
    assert enqueued == [response.data["id"]]
    assert AuditLog.objects.filter(action="run.started").exists()

    bad = start(owner.client, workflow, {"amount": "lots", "due_date": "15/11/2026", "extra": 1})
    assert bad.status_code == 422
    errors = bad.data["error"]["details"]["inputs"]
    assert set(errors) == {"vendor_name", "amount", "due_date", "extra"}


def test_start_needs_the_saved_logins(setup, enqueued) -> None:
    owner, workflow = setup
    Secret.objects.all().delete()
    response = start(owner.client, workflow)
    assert response.status_code == 409
    assert sorted(response.data["error"]["details"]["missing"]) == [
        "acme_login.password",
        "acme_login.username",
    ]
    assert Run.objects.count() == 0


def test_cancel_a_queued_run(setup, enqueued) -> None:
    owner, workflow = setup
    run_id = start(owner.client, workflow).data["id"]
    response = owner.client.post(f"/api/v1/runs/{run_id}/cancel")
    assert response.status_code == 202 and response.data["status"] == "cancelled"
    assert owner.client.post(f"/api/v1/runs/{run_id}/cancel").status_code == 409
    live.clear(run_id)


def waiting_run(owner, workflow) -> Run:
    run = Run.objects.create(
        org=owner.org,
        workflow=workflow,
        version=workflow.versions.get(version=1),
        user=owner.user,
        triggered_by="test",
        status=Run.Status.AWAITING_APPROVAL,
        current_step_id="s2",
    )
    RunStep.objects.create(
        org=owner.org,
        run=run,
        step_id="s2",
        seq=2,
        status="awaiting_approval",
        screenshot_ref="002-s2-approval.jpg",
    )
    live.clear(run.id)
    return run


def test_checkpoint_decisions(setup, make_account, django_capture_on_commit_callbacks) -> None:
    owner, workflow = setup
    run = waiting_run(owner, workflow)
    url = f"/api/v1/runs/{run.id}/checkpoints/s2"
    other_member = make_account("imran@acme.test", org=owner.org, role="member")

    assert (
        owner.client.post(
            f"/api/v1/runs/{run.id}/checkpoints/s9", {"decision": "approve"}, format="json"
        ).status_code
        == 409
    )
    denied = other_member.client.post(url, {"decision": "approve"}, format="json")
    assert denied.status_code == 403  # a member can only decide on their own runs

    with django_capture_on_commit_callbacks(execute=True):
        approved = owner.client.post(
            url, {"decision": "approve", "note": "looks right"}, format="json"
        )
    assert approved.status_code == 200 and approved.data["status"] == "running"
    assert live.wait_for_decision(run.id, 1) == "approve"  # the runner would wake up now
    decision = CheckpointDecision.objects.get(run=run)
    assert (decision.decided_by, decision.screenshot_ref) == (owner.user, "002-s2-approval.jpg")
    assert AuditLog.objects.filter(action="run.checkpoint.approved").exists()
    assert (
        owner.client.post(url, {"decision": "reject"}, format="json").status_code == 409
    )  # answered


def test_run_detail_lists_steps_and_decisions(setup) -> None:
    owner, workflow = setup
    run = waiting_run(owner, workflow)
    detail = owner.client.get(f"/api/v1/runs/{run.id}").data
    assert detail["steps"][0]["step_id"] == "s2" and detail["status"] == "awaiting_approval"
    listed = owner.client.get(f"/api/v1/workflows/{workflow.id}/runs").data["results"]
    assert [r["id"] for r in listed] == [run.id]
    assert (
        owner.client.get("/api/v1/runs?status=awaiting_approval").data["results"][0]["id"] == run.id
    )


def test_screenshots_and_isolation(setup, make_account) -> None:
    owner, workflow = setup
    run = waiting_run(owner, workflow)
    shot = owner.client.get(f"/api/v1/runs/{run.id}/screenshots/002-s2-approval.jpg")
    assert shot.status_code == 302 and run.artifacts_prefix in shot["Location"]
    assert owner.client.get(f"/api/v1/runs/{run.id}/screenshots/other.jpg").status_code == 404

    other = make_account("x@other.test")
    for url in (f"/api/v1/runs/{run.id}", f"/api/v1/runs/{run.id}/screenshots/002-s2-approval.jpg"):
        assert other.client.get(url).status_code == 404
    assert (
        other.client.post(
            f"/api/v1/runs/{run.id}/checkpoints/s2", {"decision": "approve"}, format="json"
        ).status_code
        == 404
    )
    assert start(other.client, workflow).status_code == 404


def read_events(token: str | None, run_id: str) -> tuple[int, list[dict]]:
    async def go():
        headers = {"Authorization": token} if token else {}
        response = await AsyncClient().get(f"/api/v1/runs/{run_id}/events", headers=headers)
        if response.status_code != 200:
            return response.status_code, []
        body = b"".join([chunk async for chunk in response.streaming_content])  # type: ignore[attr-defined]
        events = [
            json.loads(line[len("data: ") :])
            for line in body.decode().splitlines()
            if line.startswith("data: ")
        ]
        return response.status_code, events

    return async_to_sync(go)()


def test_live_events_stream_for_a_finished_run(setup, make_account) -> None:
    owner, workflow = setup
    run = waiting_run(owner, workflow)
    Run.objects.filter(pk=run.pk).update(status="succeeded")
    live.publish(run.id, {"type": "frame", "step_id": "s2", "jpeg_b64": "AAAA"})
    token = owner.client._credentials["HTTP_AUTHORIZATION"]

    code, events = read_events(token, run.id)
    assert code == 200
    assert [e["type"] for e in events] == ["snapshot", "frame", "done"]
    assert events[0]["run"]["id"] == run.id and events[0]["run"]["steps"][0]["step_id"] == "s2"

    assert read_events(None, run.id)[0] == 401
    other = make_account("x@other.test")
    assert read_events(other.client._credentials["HTTP_AUTHORIZATION"], run.id)[0] == 404
