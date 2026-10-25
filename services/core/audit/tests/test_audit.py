import pytest
from django.db import DatabaseError, transaction

from audit.models import AuditLog
from audit.service import purge, record

pytestmark = pytest.mark.django_db


def test_audit_rows_cannot_be_updated_or_deleted(make_account) -> None:
    account = make_account("owner@acme.test")
    entry = record("test.event", org=account.org, actor="system")

    for attempt in (
        lambda: AuditLog.objects.filter(pk=entry.pk).update(action="tampered"),
        lambda: AuditLog.objects.filter(pk=entry.pk).delete(),
    ):
        with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
            attempt()
    assert AuditLog.objects.get(pk=entry.pk).action == "test.event"


def test_explicit_purge_is_allowed(make_account) -> None:
    account = make_account("owner@acme.test")
    record("test.event", org=account.org, actor="system")
    assert purge(AuditLog.objects.for_org(account.org).filter(action="test.event")) == 1
    # the escape hatch is transaction-scoped: afterwards deletes are blocked again
    entry = record("test.event", org=account.org, actor="system")
    with pytest.raises(DatabaseError), transaction.atomic():
        AuditLog.objects.filter(pk=entry.pk).delete()


def test_owner_reads_audit_newest_first(make_account) -> None:
    account = make_account("owner@acme.test")
    record("first", org=account.org, actor="system")
    record("second", org=account.org, actor="system")
    record("third", org=account.org, actor="system")
    response = account.client.get("/api/v1/audit?limit=2")
    assert response.status_code == 200
    page = response.data["results"]
    assert len(page) == 2 and response.data["next"]  # cursor pagination
    keys = [(r["created_at"], r["id"]) for r in page]
    assert keys == sorted(keys, reverse=True)
    rest = account.client.get(response.data["next"]).data["results"]
    assert {r["action"] for r in page + rest} == {"first", "second", "third"}


def test_members_cannot_read_audit(make_account) -> None:
    owner = make_account("owner@acme.test")
    member = make_account("member@acme.test", org=owner.org, role="member")
    response = member.client.get("/api/v1/audit")
    assert response.status_code == 403
    assert response.data["error"]["code"] == "owner_required"


def test_record_captures_request_context(make_account) -> None:
    account = make_account("owner@acme.test")
    account.client.post(
        "/api/v1/tokens",
        {"name": "ext"},
        format="json",
        HTTP_USER_AGENT="pytest-agent",
        HTTP_X_FORWARDED_FOR="203.0.113.7, 10.0.0.1",
    )
    entry = AuditLog.objects.for_org(account.org).get(action="token.created")
    assert entry.actor == f"user:{account.user.pk}"
    assert entry.ip == "203.0.113.7"
    assert entry.user_agent == "pytest-agent"
