from typing import Any

import pytest

from audit.models import AuditLog
from runs.models import HealEvent, Run
from workflows.models import Workflow, WorkflowVersion
from workflows.service import create_version

pytestmark = pytest.mark.django_db

SPEC: dict[str, Any] = {
    "spec_version": "1.0",
    "name": "Invoice",
    "allowed_domains": ["acme.test"],
    "start_url": "https://acme.test/",
    "inputs": [],
    "secrets": [],
    "outputs": [],
    "steps": [
        {"id": "s1", "action": "navigate", "intent": "Open", "url": "https://acme.test/"},
        {
            "id": "s2",
            "action": "click",
            "intent": "Open the new invoice form",
            "target": {"locators": [{"kind": "role", "role": "button", "name": "New invoice"}]},
        },
    ],  # fmt: skip
    "settings": {},
}


@pytest.fixture
def healed(make_account):
    owner = make_account("sara@acme.test")
    workflow = Workflow.objects.create(org=owner.org, name="Invoice")
    v1 = create_version(workflow, SPEC, created_by="compiler", activate=True)
    run = Run.objects.create(
        org=owner.org,
        workflow=workflow,
        version=v1,
        user=owner.user,
        triggered_by="test",
        status="succeeded",
    )
    spec = {**SPEC, "steps": [SPEC["steps"][0], {**SPEC["steps"][1], "target": {"locators": [
        {"kind": "role", "role": "button", "name": "Create invoice", "exact": True},
        {"kind": "role", "role": "button", "name": "New invoice"}]}}]}  # fmt: skip
    v2 = create_version(workflow, spec, created_by="healer", parent=v1)
    WorkflowVersion.objects.filter(pk=v2.pk).update(status="pending_heal")
    heal = HealEvent.objects.create(
        org=owner.org, run=run, workflow=workflow, step_id="s2", rung="L2", score=0.86,
        before_locators=SPEC["steps"][1]["target"]["locators"],
        after_locators=[{"kind": "role", "role": "button", "name": "Create invoice", "exact": True}],
        explanation="“New invoice” is now “Create invoice”.", after_image_ref="002-s2-heal.jpg",
        resulting_version=v2,
    )  # fmt: skip
    return owner, workflow, heal


def test_list_and_detail(healed) -> None:
    owner, workflow, heal = healed
    listed = owner.client.get(f"/api/v1/heals?workflow_id={workflow.id}&decision=pending").data[
        "results"
    ]
    assert [h["id"] for h in listed] == [heal.id]
    assert listed[0]["step_intent"] == "Open the new invoice form"
    assert listed[0]["resulting_version"] == {"version": 2, "status": "pending_heal"}
    assert owner.client.get("/api/v1/workflows").data["results"][0]["pending_heals"] == 1
    shot = owner.client.get(f"/api/v1/runs/{heal.run_id}/screenshots/002-s2-heal.jpg")
    assert shot.status_code == 302


def test_owner_approves_and_the_healed_version_becomes_active(healed) -> None:
    owner, workflow, heal = healed
    response = owner.client.post(
        f"/api/v1/heals/{heal.id}/decision", {"decision": "approve"}, format="json"
    )
    assert response.status_code == 200 and response.data["decision"] == "approved"
    workflow.refresh_from_db()
    assert workflow.active_version.version == 2
    assert dict(workflow.versions.values_list("version", "status")) == {1: "archived", 2: "active"}
    assert AuditLog.objects.filter(action="heal.approved").exists()
    again = owner.client.post(
        f"/api/v1/heals/{heal.id}/decision", {"decision": "reject"}, format="json"
    )
    assert again.status_code == 409


def test_reject_archives_the_healed_version(healed) -> None:
    owner, workflow, heal = healed
    response = owner.client.post(
        f"/api/v1/heals/{heal.id}/decision", {"decision": "reject"}, format="json"
    )
    assert response.data["decision"] == "rejected"
    workflow.refresh_from_db()
    assert workflow.active_version.version == 1
    assert workflow.versions.get(version=2).status == "archived"


def test_only_owners_decide_and_other_workspaces_see_nothing(healed, make_account) -> None:
    owner, _, heal = healed
    member = make_account("imran@acme.test", org=owner.org, role="member")
    assert member.client.get(f"/api/v1/heals/{heal.id}").status_code == 200
    assert (
        member.client.post(
            f"/api/v1/heals/{heal.id}/decision", {"decision": "approve"}, format="json"
        ).status_code
        == 403
    )
    other = make_account("x@other.test")
    assert other.client.get(f"/api/v1/heals/{heal.id}").status_code == 404
    assert (
        other.client.post(
            f"/api/v1/heals/{heal.id}/decision", {"decision": "approve"}, format="json"
        ).status_code
        == 404
    )
    assert other.client.get("/api/v1/heals").data["results"] == []
