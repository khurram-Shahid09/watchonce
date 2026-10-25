import copy
from decimal import Decimal
from pathlib import Path

import pytest
from django.test import override_settings

from audit.models import AuditLog
from common.storage import MemoryStorage, get_storage
from engine.llm.types import Usage
from metering.models import LlmCall
from metering.service import cost_of
from recordings.models import Recording
from workflows.models import Workflow, WorkflowVersion

pytestmark = pytest.mark.django_db

FIXTURE = Path(__file__).parents[2] / "engine/compiler/tests/fixtures/acme_v2_create_invoice.json"


@pytest.fixture
def storage() -> MemoryStorage:
    store = get_storage()
    assert isinstance(store, MemoryStorage)
    store.objects.clear()
    return store


def upload_and_compile(account, storage, django_capture_on_commit_callbacks) -> dict:
    """Extension flow end to end, compiled by the fake provider (LLM_PROVIDER=fake in tests)."""
    body = {
        "description": "Create a vendor invoice",
        "start_url": "http://localhost:3001/login",
        "event_count": 29,
        "frames": ["frames/0002.webp", "frames/0004.webp"],
    }
    rec_id = account.client.post("/api/v1/recordings", body, format="json").data["id"]
    rec = Recording.objects.get(pk=rec_id)
    storage.put_bytes(rec.key("events.json"), FIXTURE.read_bytes(), "application/json")
    for name in rec.frame_names:
        storage.put_bytes(rec.key(name), b"RIFF....WEBP", "image/webp")
    with django_capture_on_commit_callbacks(execute=True):
        account.client.post(f"/api/v1/recordings/{rec_id}/complete")
    return account.client.get(f"/api/v1/recordings/{rec_id}").data


@pytest.fixture
def compiled(make_account, storage, django_capture_on_commit_callbacks):
    owner = make_account("sara@acme.test")
    recording = upload_and_compile(owner, storage, django_capture_on_commit_callbacks)
    return owner, recording


def test_upload_compiles_into_an_active_workflow_with_an_sop(compiled) -> None:
    owner, recording = compiled
    assert recording["status"] == "compiled"
    assert recording["workflow_id"].startswith("wf_")

    listed = owner.client.get("/api/v1/workflows").data["results"]
    assert [w["id"] for w in listed] == [recording["workflow_id"]]
    assert listed[0]["active_version"]["version"] == 1
    assert listed[0]["step_count"] == 12

    version = owner.client.get(f"/api/v1/workflows/{recording['workflow_id']}/versions/1").data
    assert version["status"] == "active" and version["created_by"] == "compiler"
    assert version["spec"]["source"]["recording_id"] == recording["id"]
    assert version["sop_markdown"].startswith("# Create a vendor invoice")
    assert "screenshot:frames/0002.webp" in version["sop_markdown"]
    assert version["compile_info"]["understand"]["by"] == "fake:fake-understand-v1"
    assert LlmCall.objects.filter(entity_id=recording["id"], purpose="understand").count() == 1
    assert AuditLog.objects.filter(action="recording.compiled", entity_id=recording["id"]).exists()


def test_saving_an_edit_creates_the_next_version(compiled) -> None:
    owner, recording = compiled
    base = f"/api/v1/workflows/{recording['workflow_id']}"
    spec = copy.deepcopy(owner.client.get(f"{base}/versions/1").data["spec"])
    spec["name"] = "Create invoice (edited)"
    spec["steps"][1]["intent"] = "Type the user ID"

    response = owner.client.post(
        f"{base}/versions",
        {"spec": spec, "change_note": "clearer intent", "base_version": 1},
        format="json",
    )
    assert response.status_code == 201, response.content
    assert response.data["version"] == 2 and response.data["status"] == "draft"
    assert response.data["parent_version_id"] == owner.client.get(f"{base}/versions/1").data["id"]

    detail = owner.client.get(base).data
    assert detail["name"] == "Create invoice (edited)"
    assert detail["active_version"]["version"] == 1  # a draft until activated
    assert [v["version"] for v in owner.client.get(f"{base}/versions").data] == [2, 1]

    activated = owner.client.post(f"{base}/versions/2/activate")
    assert activated.status_code == 200 and activated.data["status"] == "active"
    statuses = dict(WorkflowVersion.objects.values_list("version", "status"))
    assert statuses == {1: "archived", 2: "active"}


def test_invalid_spec_is_rejected_with_the_validator_errors(compiled) -> None:
    owner, recording = compiled
    base = f"/api/v1/workflows/{recording['workflow_id']}"
    spec = copy.deepcopy(owner.client.get(f"{base}/versions/1").data["spec"])
    spec["steps"][0]["url"] = "https://evil.example.com/login"
    spec["steps"][7]["value"] = "{{undefined_input}}"

    response = owner.client.post(f"{base}/versions", {"spec": spec}, format="json")
    assert response.status_code == 422
    assert response.data["error"]["code"] == "invalid_spec"
    messages = " ".join(e["message"] for e in response.data["error"]["details"]["errors"])
    assert "allowed_domains" in messages and "undefined_input" in messages
    assert WorkflowVersion.objects.count() == 1


def test_removing_a_checkpoint_is_audited(compiled) -> None:
    owner, recording = compiled
    base = f"/api/v1/workflows/{recording['workflow_id']}"
    spec = copy.deepcopy(owner.client.get(f"{base}/versions/1").data["spec"])
    guarded = [s for s in spec["steps"] if s.get("checkpoint")]
    assert guarded, "the fake provider checkpoints 'Submit for approval'"
    for s in guarded:
        del s["checkpoint"]
    assert owner.client.post(f"{base}/versions", {"spec": spec}, format="json").status_code == 201
    entry = AuditLog.objects.get(action="workflow.checkpoint.removed")
    assert entry.metadata["intents"] == [guarded[0]["intent"]]


def test_members_can_edit_but_only_owners_activate(compiled, make_account) -> None:
    owner, recording = compiled
    member = make_account("imran@acme.test", org=owner.org, role="member")
    base = f"/api/v1/workflows/{recording['workflow_id']}"
    spec = member.client.get(f"{base}/versions/1").data["spec"]

    assert member.client.post(f"{base}/versions", {"spec": spec}, format="json").status_code == 201
    denied = member.client.post(f"{base}/versions", {"spec": spec, "activate": True}, format="json")
    assert denied.status_code == 403
    assert member.client.post(f"{base}/versions/2/activate").status_code == 403
    assert owner.client.post(f"{base}/versions/2/activate").status_code == 200


def test_workflows_are_invisible_to_other_workspaces(compiled, make_account) -> None:
    _, recording = compiled
    other = make_account("x@other.test")
    base = f"/api/v1/workflows/{recording['workflow_id']}"
    for url in (
        base,
        f"{base}/versions",
        f"{base}/versions/1",
        f"{base}/screenshots/frames/0002.webp",
    ):
        assert other.client.get(url).status_code == 404, url
    assert other.client.post(f"{base}/versions/1/activate").status_code == 404
    assert other.client.get("/api/v1/workflows").data["results"] == []


def test_screenshots_redirect_to_short_lived_links(compiled) -> None:
    owner, recording = compiled
    base = f"/api/v1/workflows/{recording['workflow_id']}/screenshots"
    response = owner.client.get(f"{base}/frames/0002.webp")
    assert response.status_code == 302
    assert f"rec/{recording['id']}/frames/0002.webp" in response["Location"]
    assert owner.client.get(f"{base}/frames/9999.webp").status_code == 404
    assert owner.client.get(f"{base}/events.json").status_code == 404  # only frames


def test_rename_archive_and_sop_regeneration(compiled) -> None:
    owner, recording = compiled
    base = f"/api/v1/workflows/{recording['workflow_id']}"
    renamed = owner.client.patch(
        base, {"name": "Invoices", "manual_duration_sec": 300}, format="json"
    )
    assert renamed.status_code == 200 and renamed.data["manual_duration_sec"] == 300

    sop = owner.client.post(f"{base}/versions/1/sop")
    assert sop.status_code == 200 and sop.data["sop_markdown"].startswith("#")
    assert LlmCall.objects.filter(purpose="sop").count() == 2  # compile + regenerate

    assert owner.client.delete(base).status_code == 204
    assert owner.client.get("/api/v1/workflows").data["results"] == []
    assert Workflow.objects.get().archived_at is not None


@override_settings(LLM_MONTHLY_BUDGET_USD=1)
def test_budget_stops_compiles(make_account, storage, django_capture_on_commit_callbacks) -> None:
    owner = make_account("sara@acme.test")
    LlmCall.objects.create(org=owner.org, purpose="understand", provider="claude", model="claude-opus-5-5", cost_usd=Decimal("1.5"))  # fmt: skip
    recording = upload_and_compile(owner, storage, django_capture_on_commit_callbacks)
    assert recording["status"] == "failed"
    assert recording["error_code"] == "budget_exceeded"

    retry = owner.client.post(f"/api/v1/recordings/{recording['id']}/compile")
    assert retry.status_code == 202  # allowed; it will fail again until the budget resets


def test_cost_of_claude_calls() -> None:
    usage = Usage(provider="claude", model="claude-opus-5-5", input_tokens=25_000, output_tokens=6_000, cache_read_tokens=8_000)  # fmt: skip
    assert cost_of(usage) == Decimal("0.2216")  # docs/06: about $0.22 per compile
    assert cost_of(Usage(provider="gemini", model="gemini-3.5-flash", input_tokens=10**6)) == 0


def test_unusable_answer_is_retried_once_with_the_problems(
    make_account, storage, django_capture_on_commit_callbacks, monkeypatch
) -> None:
    from engine.compiler import pipeline
    from engine.llm.fake import FakeProvider

    seen_feedback: list[list[str]] = []

    class ForgetfulProvider(FakeProvider):
        def understand(self, req):
            seen_feedback.append(list(req.feedback))
            result, usage = super().understand(req)
            if not req.feedback:
                result.steps = result.steps[:-1]  # first answer misses the last candidate
            return result, usage

    monkeypatch.setattr(pipeline, "get_provider", lambda stage: ForgetfulProvider())
    owner = make_account("sara@acme.test")
    recording = upload_and_compile(owner, storage, django_capture_on_commit_callbacks)

    assert recording["status"] == "compiled"
    assert seen_feedback == [[], ["steps is missing candidates c12"]]
    version = WorkflowVersion.objects.get()
    assert version.compile_info["understand"]["attempts"] == 2


def test_answer_still_unusable_after_retry_fails_the_compile(
    make_account, storage, django_capture_on_commit_callbacks, monkeypatch
) -> None:
    from engine.compiler import pipeline
    from engine.llm.fake import FakeProvider

    class BrokenProvider(FakeProvider):
        def understand(self, req):
            result, usage = super().understand(req)
            result.steps = []
            return result, usage

    monkeypatch.setattr(pipeline, "get_provider", lambda stage: BrokenProvider())
    owner = make_account("sara@acme.test")
    recording = upload_and_compile(owner, storage, django_capture_on_commit_callbacks)
    assert recording["status"] == "failed"
    assert recording["error_code"] == "compile_invalid"
    assert "steps is missing candidates" in recording["error"]
    assert LlmCall.objects.filter(purpose="understand").count() == 2


def test_sop_rewrite_reports_an_unavailable_ai(compiled, monkeypatch) -> None:
    from engine.compiler import pipeline
    from engine.llm import LLMError
    from engine.llm.fake import FakeProvider

    class DownProvider(FakeProvider):
        def write_sop(self, req):
            raise LLMError("llm_unavailable", "Gemini is busy.", retryable=True)

    monkeypatch.setattr(pipeline, "get_provider", lambda stage: DownProvider())
    owner, recording = compiled
    base = f"/api/v1/workflows/{recording['workflow_id']}/versions/1"
    before = owner.client.get(base).data["sop_markdown"]
    response = owner.client.post(f"{base}/sop")
    assert response.status_code == 503
    assert response.data["error"]["code"] == "llm_unavailable"
    assert owner.client.get(base).data["sop_markdown"] == before


def test_duplicate_compile_tasks_do_not_compile_twice(compiled) -> None:
    from engine.compiler.tasks import compile_recording

    owner, recording = compiled
    calls = LlmCall.objects.count()
    # A redelivered or stray task for a recording that is already compiled: no-op.
    compile_recording.apply(args=[recording["id"]], task_id="stray-1")
    # Even if it were back in "uploaded", the existing workflow is reused, not duplicated.
    Recording.objects.filter(pk=recording["id"]).update(status="uploaded")
    compile_recording.apply(args=[recording["id"]], task_id="stray-2")

    assert Workflow.objects.count() == 1
    assert LlmCall.objects.count() == calls
    assert owner.client.get(f"/api/v1/recordings/{recording['id']}").data["status"] == "compiled"


def test_a_compile_in_progress_belongs_to_its_task(compiled) -> None:
    from engine.compiler.tasks import compile_recording

    _, recording = compiled
    Workflow.objects.all().delete()
    Recording.objects.filter(pk=recording["id"]).update(
        status="compiling", compile_task_id="owner-task"
    )
    compile_recording.apply(args=[recording["id"]], task_id="someone-else")
    assert Recording.objects.get(pk=recording["id"]).status == "compiling"  # untouched
    assert Workflow.objects.count() == 0
