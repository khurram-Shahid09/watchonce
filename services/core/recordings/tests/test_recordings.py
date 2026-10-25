import json
from pathlib import Path

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from audit.models import AuditLog
from common.storage import MemoryStorage, get_storage
from recordings.models import Recording

pytestmark = pytest.mark.django_db

FIXTURE = Path(__file__).parents[2] / "engine/compiler/tests/fixtures/acme_v2_create_invoice.json"
BODY = {
    "description": "Create a vendor invoice",
    "start_url": "http://localhost:3001/login",
    "event_count": 29,
    "duration_ms": 30_900,
    "frames": ["frames/0002.webp", "frames/0001.webp"],
}


@pytest.fixture
def storage() -> MemoryStorage:
    store = get_storage()
    assert isinstance(store, MemoryStorage)
    store.objects.clear()
    return store


def create(client: APIClient, **overrides) -> dict:
    response = client.post("/api/v1/recordings", {**BODY, **overrides}, format="json")
    assert response.status_code == 201, response.content
    return response.data


def upload_all(storage: MemoryStorage, rec_id: str, events: bytes | None = None) -> None:
    rec = Recording.objects.get(pk=rec_id)
    storage.put_bytes(rec.key("events.json"), events or FIXTURE.read_bytes(), "application/json")
    for name in rec.frame_names:
        storage.put_bytes(rec.key(name), b"RIFF....WEBP", "image/webp")


def test_create_returns_presigned_urls_for_every_file(make_account, storage) -> None:
    a = make_account("sara@acme.test")
    data = create(a.client)
    assert data["id"].startswith("rec_")
    assert data["status"] == "uploading"
    assert data["frame_count"] == 2
    prefix = f"org/{a.org.id}/rec/{data['id']}/"
    assert data["upload"]["events_url"].startswith(f"memory://{prefix}events.json")
    assert [f["name"] for f in data["upload"]["frames"]] == ["frames/0001.webp", "frames/0002.webp"]
    assert data["upload"]["frames"][0]["url"].startswith(f"memory://{prefix}frames/0001.webp")
    assert AuditLog.objects.filter(action="recording.created", entity_id=data["id"]).exists()


@pytest.mark.parametrize(
    "overrides",
    [
        {"description": ""},
        {"start_url": "chrome://extensions"},
        {"start_url": "file:///etc/passwd"},
        {"event_count": 0},
        {"frames": ["frames/0001.webp", "frames/0001.webp"]},
        {"frames": ["../../other-org/x.webp"]},
        {"frames": ["frames/0001.png"]},
    ],
)
def test_create_validates_input(make_account, storage, overrides) -> None:
    a = make_account("sara@acme.test")
    response = a.client.post("/api/v1/recordings", {**BODY, **overrides}, format="json")
    assert response.status_code == 400
    assert response.data["error"]["code"] == "validation_error"


def test_complete_requires_every_file(make_account, storage) -> None:
    a = make_account("sara@acme.test")
    rec_id = create(a.client)["id"]
    rec = Recording.objects.get(pk=rec_id)
    storage.put_bytes(rec.key("events.json"), b"{}", "application/json")

    response = a.client.post(f"/api/v1/recordings/{rec_id}/complete")
    assert response.status_code == 409
    assert response.data["error"]["code"] == "upload_incomplete"
    assert response.data["error"]["details"]["missing"] == ["frames/0001.webp", "frames/0002.webp"]
    assert Recording.objects.get(pk=rec_id).status == "uploading"


@override_settings(RECORDING_MAX_FRAME_BYTES=4)
def test_complete_rejects_oversized_files(make_account, storage) -> None:
    a = make_account("sara@acme.test")
    rec_id = create(a.client)["id"]
    upload_all(storage, rec_id)
    response = a.client.post(f"/api/v1/recordings/{rec_id}/complete")
    assert response.status_code == 413
    assert response.data["error"]["details"]["files"] == ["frames/0001.webp", "frames/0002.webp"]


def test_complete_normalizes_and_is_idempotent(
    make_account, storage, django_capture_on_commit_callbacks
) -> None:
    a = make_account("sara@acme.test")
    rec_id = create(a.client)["id"]
    upload_all(storage, rec_id)

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        response = a.client.post(f"/api/v1/recordings/{rec_id}/complete")
    assert response.status_code == 202
    assert response.data["status"] == "uploaded"
    assert len(callbacks) == 1  # compile enqueued (runs eagerly in tests)

    detail = a.client.get(f"/api/v1/recordings/{rec_id}").data
    assert detail["candidate_count"] == 12
    assert detail["uploaded_at"] is not None

    candidates = a.client.get(f"/api/v1/recordings/{rec_id}/candidates").data
    assert candidates["stats"]["raw_events"] == 29
    assert candidates["candidates"][2]["value"] == "__SECRET__"

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        again = a.client.post(f"/api/v1/recordings/{rec_id}/complete")
    assert again.status_code == 202
    assert callbacks == []  # not enqueued twice
    assert AuditLog.objects.filter(action="recording.uploaded", entity_id=rec_id).count() == 1


def test_invalid_events_file_fails_cleanly(
    make_account, storage, django_capture_on_commit_callbacks
) -> None:
    a = make_account("sara@acme.test")
    rec_id = create(a.client)["id"]
    upload_all(storage, rec_id, events=json.dumps({"format_version": 99}).encode())
    with django_capture_on_commit_callbacks(execute=True):
        a.client.post(f"/api/v1/recordings/{rec_id}/complete")
    detail = a.client.get(f"/api/v1/recordings/{rec_id}").data
    assert detail["status"] == "failed"
    assert "invalid" in detail["error"]
    response = a.client.get(f"/api/v1/recordings/{rec_id}/candidates")
    assert response.status_code == 409
    assert response.data["error"]["code"] == "candidates_not_ready"


def test_extension_uploads_with_a_personal_access_token(make_account, storage) -> None:
    a = make_account("sara@acme.test")
    raw = a.client.post("/api/v1/tokens", {"name": "Chrome"}, format="json").data["token"]
    ext = APIClient()
    ext.credentials(HTTP_AUTHORIZATION=f"Bearer {raw}")
    rec_id = create(ext)["id"]
    assert Recording.objects.get(pk=rec_id).org_id == a.org.id
    assert [r["id"] for r in a.client.get("/api/v1/recordings").data["results"]] == [rec_id]


def test_recordings_are_invisible_to_other_workspaces(make_account, storage) -> None:
    a = make_account("a@alpha.test")
    b = make_account("b@beta.test")
    rec_id = create(a.client)["id"]
    upload_all(storage, rec_id)
    for url in (f"/api/v1/recordings/{rec_id}", f"/api/v1/recordings/{rec_id}/candidates"):
        assert b.client.get(url).status_code == 404
    assert b.client.post(f"/api/v1/recordings/{rec_id}/complete").status_code == 404
    assert b.client.get("/api/v1/recordings").data["results"] == []
    assert Recording.objects.get(pk=rec_id).status == "uploading"


def test_requires_authentication(storage) -> None:
    assert APIClient().post("/api/v1/recordings", BODY, format="json").status_code == 401
