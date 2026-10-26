from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import override_settings
from django.utils import timezone

from metering.models import LlmCall
from runs.models import HealEvent, Run
from runs.tests.test_runs_api import INPUTS, SPEC, start
from secrets_vault.models import Secret
from workflows.models import Workflow
from workflows.service import create_version

pytestmark = pytest.mark.django_db


@pytest.fixture
def workflow(make_account):
    owner = make_account("sara@acme.test")
    wf = Workflow.objects.create(org=owner.org, name="Create invoice", manual_duration_sec=600)
    create_version(wf, SPEC, created_by="test", activate=True)
    secret = Secret(org=owner.org, name="acme_login")
    secret.set_values({"username": "sara", "password": "acme-demo"})
    secret.save()
    return owner, wf


def add_run(wf, status: str, days_ago: int = 0) -> Run:
    wf.refresh_from_db()
    run = Run.objects.create(
        org=wf.org, workflow=wf, version=wf.active_version, triggered_by="test", status=status
    )
    Run.objects.filter(pk=run.pk).update(created_at=timezone.now() - timedelta(days=days_ago))
    run.refresh_from_db()
    return run


def test_summary_counts_hours_saved_heals_and_spend(workflow, make_account) -> None:
    owner, wf = workflow
    for status in ("succeeded", "succeeded", "succeeded", "failed", "running"):
        add_run(wf, status)
    old = add_run(wf, "succeeded", days_ago=10)  # outside 7d, inside 30d
    heal = HealEvent.objects.create(
        org=owner.org, run=old, workflow=wf, step_id="s2", rung="L2", score=0.9, explanation="x"
    )
    HealEvent.objects.filter(pk=heal.pk).update(created_at=old.created_at)
    LlmCall.objects.create(
        org=owner.org, purpose="understand", provider="claude", model="m", cost_usd=Decimal("0.42")
    )
    # Another workspace's runs never count.
    other = make_account("eve@other.test")
    other_wf = Workflow.objects.create(org=other.org, name="X", manual_duration_sec=999)
    create_version(other_wf, SPEC, created_by="test", activate=True)
    add_run(other_wf, "succeeded")

    week = owner.client.get("/api/v1/analytics/summary?range=7d")
    assert week.status_code == 200, week.content
    data = week.data
    assert (data["runs"], data["succeeded"]) == (5, 3)
    assert data["success_rate"] == pytest.approx(3 / 4)  # the running one isn't finished
    assert data["hours_saved"] == pytest.approx(0.5)  # 3 × 10 minutes
    assert data["heals"] == 0 and data["llm_spend_usd"] == "0.4200"
    assert len(data["daily"]) == 7 and data["daily"][-1]["succeeded"] == 3
    assert data["workflows"][0]["workflow_id"] == wf.id

    month = owner.client.get("/api/v1/analytics/summary?range=30d").data
    assert month["succeeded"] == 4 and month["heals"] == 1 and month["heals_pending"] == 1

    assert owner.client.get("/api/v1/analytics/summary?range=1y").status_code == 400


def test_workflows_without_a_manual_time_are_flagged(workflow) -> None:
    owner, wf = workflow
    Workflow.objects.filter(pk=wf.pk).update(manual_duration_sec=None)
    add_run(wf, "succeeded")
    data = owner.client.get("/api/v1/analytics/summary").data
    assert data["hours_saved"] == 0 and data["workflows_without_duration"] == 1


@override_settings(ORG_RUNS_PER_HOUR=2)
def test_runs_per_hour_per_workspace(workflow, monkeypatch) -> None:
    monkeypatch.setattr("runs.views._enqueue_run", lambda run_id: None)
    owner, wf = workflow
    assert start(owner.client, wf).status_code == 202
    assert start(owner.client, wf).status_code == 202
    blocked = start(owner.client, wf, INPUTS)
    assert blocked.status_code == 429
    assert blocked.data["error"]["code"] == "rate_limited"
    assert Run.objects.count() == 2


@override_settings(ORG_COMPILES_PER_HOUR=1)
def test_compiles_per_hour_per_workspace(workflow) -> None:
    from audit.models import AuditLog
    from common import quotas
    from common.exceptions import ApiError

    owner, _ = workflow
    quotas.check_compiles(owner.org)
    AuditLog.objects.create(org=owner.org, actor="system", action="recording.uploaded")
    with pytest.raises(ApiError) as exc:
        quotas.check_compiles(owner.org)
    assert exc.value.status_code == 429


def test_general_limit_per_token(workflow, monkeypatch) -> None:
    from common.throttles import TokenRateThrottle

    monkeypatch.setattr(TokenRateThrottle, "THROTTLE_RATES", {"token": "3/min"})
    owner, _ = workflow
    codes = [owner.client.get("/api/v1/workflows").status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
