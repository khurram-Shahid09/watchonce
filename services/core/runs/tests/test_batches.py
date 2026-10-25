import csv
import io
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from audit.models import AuditLog
from runs.models import Batch, CheckpointDecision, Run
from secrets_vault.models import Secret
from workflows.models import Workflow
from workflows.service import create_version

pytestmark = pytest.mark.django_db

SPEC: dict[str, Any] = {
    "spec_version": "1.0",
    "name": "Create invoice",
    "allowed_domains": ["acme.test"],
    "start_url": "https://acme.test/",
    "inputs": [
        {"name": "vendor_name", "type": "string", "required": True},
        {"name": "amount", "type": "number", "required": True},
        {"name": "due_date", "type": "date", "required": True},
    ],
    "secrets": [{"name": "acme_login", "fields": ["password"]}],
    "outputs": [{"name": "invoice_number", "type": "string"}],
    "steps": [
        {"id": "s1", "action": "navigate", "intent": "Open", "url": "https://acme.test/"},
        {
            "id": "s2",
            "action": "extract",
            "intent": "Read",
            "output": "invoice_number",
            "target": {"locators": [{"kind": "css", "value": "body"}]},
        },
    ],  # fmt: skip
    "settings": {},
}
CSV = "Vendor Name,Amount,Due Date,Notes\nNorthwind Ltd,1250.50,2026-11-15,first\nCity Power,99,2026-12-01,second\n"


@pytest.fixture
def setup(make_account):
    owner = make_account("sara@acme.test")
    workflow = Workflow.objects.create(org=owner.org, name="Create invoice")
    create_version(workflow, SPEC, created_by="test", activate=True)
    secret = Secret(org=owner.org, name="acme_login")
    secret.set_values({"password": "x"})
    secret.save()
    return owner, workflow


@pytest.fixture
def enqueued(monkeypatch) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr("runs.views._enqueue_batch", calls.append)
    return calls


def upload(client, workflow, body: str = CSV, **extra):
    file = SimpleUploadedFile("invoices.csv", body.encode(), content_type="text/csv")
    return client.post(
        f"/api/v1/workflows/{workflow.id}/batches", {"file": file, **extra}, format="multipart"
    )


def test_upload_matches_columns_and_queues_one_run_per_row(
    setup, enqueued, django_capture_on_commit_callbacks
) -> None:
    owner, workflow = setup
    with django_capture_on_commit_callbacks(execute=True):
        response = upload(owner.client, workflow)
    assert response.status_code == 202, response.content
    assert response.data["total"] == 2 and response.data["status"] == "queued"
    assert response.data["column_map"] == {
        "vendor_name": "Vendor Name",
        "amount": "Amount",
        "due_date": "Due Date",
    }
    assert enqueued == [response.data["id"]]
    runs = list(Run.objects.filter(batch_id=response.data["id"]).order_by("row_index"))
    assert [(r.row_index, r.inputs["amount"], r.status) for r in runs] == [
        (1, 1250.5, "queued"),
        (2, 99.0, "queued"),
    ]
    assert AuditLog.objects.filter(action="batch.started").exists()


def test_bad_rows_start_nothing(setup, enqueued) -> None:
    owner, workflow = setup
    body = "Vendor Name,Amount,Due Date\nNorthwind,lots,2026-11-15\n,5,15/11/2026\n"
    response = upload(owner.client, workflow, body)
    assert response.status_code == 422
    errors = response.data["error"]["details"]["errors"]
    assert set(errors) == {"row 1", "row 2"}
    assert set(errors["row 2"]) == {"vendor_name", "due_date"}
    assert Batch.objects.count() == 0 and enqueued == []


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ("", "invalid_file"),
        ("Vendor Name,Amount\n", "invalid_file"),
        ("Vendor,Total\nNorthwind,5\n", "invalid_rows"),  # no column for the inputs
    ],
)
def test_unusable_files(setup, enqueued, body, code) -> None:
    owner, workflow = setup
    response = upload(owner.client, workflow, body)
    assert response.status_code in (400, 422)
    if response.status_code == 422:
        assert response.data["error"]["code"] == code


def test_explicit_column_map_and_missing_logins(setup, enqueued) -> None:
    owner, workflow = setup
    body = "Supplier,Total,When\nNorthwind,5,2026-11-15\n"
    mapping = '{"vendor_name": "Supplier", "amount": "Total", "due_date": "When"}'
    assert upload(owner.client, workflow, body, column_map=mapping).status_code == 202
    Secret.objects.all().delete()
    response = upload(owner.client, workflow, body, column_map=mapping)
    assert response.status_code == 409 and response.data["error"]["code"] == "missing_secrets"


def test_approve_all_is_owner_only_and_approves_the_waiting_row(
    setup, make_account, enqueued, django_capture_on_commit_callbacks
) -> None:
    owner, workflow = setup
    batch_id = upload(owner.client, workflow).data["id"]
    waiting = Run.objects.get(batch_id=batch_id, row_index=1)
    Run.objects.filter(pk=waiting.pk).update(status="awaiting_approval", current_step_id="s2")
    Batch.objects.filter(pk=batch_id).update(status="running")

    member = make_account("imran@acme.test", org=owner.org, role="member")
    assert member.client.post(f"/api/v1/batches/{batch_id}/approve-all").status_code == 403
    with django_capture_on_commit_callbacks(execute=True):
        response = owner.client.post(f"/api/v1/batches/{batch_id}/approve-all")
    assert response.status_code == 200 and response.data["approve_all"] is True
    decision = CheckpointDecision.objects.get(run=waiting)
    assert decision.decision == "approve" and decision.note == "Approved for the whole batch"
    assert Run.objects.get(pk=waiting.pk).status == "running"


def test_results_csv_and_cancel(setup, enqueued) -> None:
    owner, workflow = setup
    batch_id = upload(owner.client, workflow).data["id"]
    Run.objects.filter(batch_id=batch_id, row_index=1).update(
        status="succeeded", outputs={"invoice_number": "INV-7"}
    )
    Run.objects.filter(batch_id=batch_id, row_index=2).update(
        status="failed", error_message="Step s2 failed"
    )

    response = owner.client.get(f"/api/v1/batches/{batch_id}/results.csv")
    assert response.status_code == 200 and response["Content-Type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert [(r["Vendor Name"], r["Notes"], r["status"], r["invoice_number"]) for r in rows] == [
        ("Northwind Ltd", "first", "succeeded", "INV-7"),
        ("City Power", "second", "failed", ""),
    ]
    assert rows[1]["error"] == "Step s2 failed"

    Run.objects.filter(batch_id=batch_id, row_index=2).update(status="queued")
    cancelled = owner.client.post(f"/api/v1/batches/{batch_id}/cancel")
    assert cancelled.status_code == 202 and cancelled.data["status"] == "cancelled"
    assert Run.objects.get(batch_id=batch_id, row_index=2).status == "cancelled"
    assert owner.client.post(f"/api/v1/batches/{batch_id}/cancel").status_code == 409


def test_batch_task_runs_rows_in_order_and_counts(setup, enqueued, monkeypatch) -> None:
    from engine.runner import tasks

    owner, workflow = setup
    batch_id = upload(owner.client, workflow).data["id"]
    order: list[int] = []

    class FakeExecutor:
        def __init__(self, run, browser) -> None:
            self.run = run

        def execute(self) -> None:
            order.append(self.run.row_index)
            self.run.status = "succeeded" if self.run.row_index == 1 else "failed"
            self.run.save(update_fields=["status"])

    monkeypatch.setattr("engine.runner.executor.Executor", FakeExecutor)
    monkeypatch.setattr("engine.runner.browser.get_browser", lambda: None)
    # The worker closes its DB connections afterwards; here that would close the test's.
    monkeypatch.setattr(tasks.db.connections, "close_all", lambda: None)
    tasks.execute_batch(batch_id)

    batch = Batch.objects.get(pk=batch_id)
    assert order == [1, 2]
    assert (batch.status, batch.succeeded, batch.failed) == ("finished", 1, 1)
    detail = owner.client.get(f"/api/v1/batches/{batch_id}").data
    assert [r["status"] for r in sorted(detail["runs"], key=lambda r: r["row_index"])] == [
        "succeeded",
        "failed",
    ]


def test_batches_are_invisible_to_other_workspaces(setup, make_account, enqueued) -> None:
    owner, workflow = setup
    batch_id = upload(owner.client, workflow).data["id"]
    other = make_account("x@other.test")
    for url in (f"/api/v1/batches/{batch_id}", f"/api/v1/batches/{batch_id}/results.csv"):
        assert other.client.get(url).status_code == 404
    assert other.client.post(f"/api/v1/batches/{batch_id}/approve-all").status_code == 404
    assert upload(other.client, workflow).status_code == 404
