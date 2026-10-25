import pytest

from accounts.models import Membership
from audit.models import AuditLog

pytestmark = pytest.mark.django_db


@pytest.fixture
def team(make_account):
    owner = make_account("owner@acme.test")
    member = make_account("member@acme.test", org=owner.org, role="member")
    return owner, member


def members_url(org_id: str, member_id: str | None = None) -> str:
    base = f"/api/v1/orgs/{org_id}/members"
    return f"{base}/{member_id}" if member_id else base


def test_members_can_list_members(team) -> None:
    owner, member = team
    response = member.client.get(members_url(owner.org.id))
    assert response.status_code == 200
    emails = {m["user"]["email"] for m in response.data["results"]}
    assert emails == {"owner@acme.test", "member@acme.test"}


def test_owner_adds_existing_user(team, make_account) -> None:
    owner, _ = team
    make_account("newhire@acme.test")  # has their own workspace already
    response = owner.client.post(
        members_url(owner.org.id), {"email": "NewHire@acme.test"}, format="json"
    )
    assert response.status_code == 201
    assert response.data["role"] == "member"
    assert AuditLog.objects.for_org(owner.org).filter(action="member.added").exists()


@pytest.mark.parametrize(
    ("email", "status", "code"),
    [("nobody@acme.test", 404, "user_not_found"), ("member@acme.test", 409, "already_member")],
)
def test_add_member_errors(team, email, status, code) -> None:
    owner, _ = team
    response = owner.client.post(members_url(owner.org.id), {"email": email}, format="json")
    assert response.status_code == status
    assert response.data["error"]["code"] == code


def test_members_cannot_manage_members(team) -> None:
    owner, member = team
    add = member.client.post(members_url(owner.org.id), {"email": "x@acme.test"}, format="json")
    assert add.status_code == 403
    assert add.data["error"]["code"] == "owner_required"
    promote = member.client.patch(
        members_url(owner.org.id, member.membership.id), {"role": "owner"}, format="json"
    )
    assert promote.status_code == 403
    assert Membership.objects.get(pk=member.membership.pk).role == "member"


def test_owner_changes_role_and_removes_member(team) -> None:
    owner, member = team
    url = members_url(owner.org.id, member.membership.id)
    assert owner.client.patch(url, {"role": "owner"}, format="json").data["role"] == "owner"
    assert owner.client.delete(url).status_code == 204
    assert not Membership.objects.filter(pk=member.membership.pk).exists()
    actions = list(AuditLog.objects.for_org(owner.org).values_list("action", flat=True))
    assert "member.role_changed" in actions and "member.removed" in actions


def test_last_owner_cannot_leave_or_be_demoted(team) -> None:
    owner, _ = team
    url = members_url(owner.org.id, owner.membership.id)
    demote = owner.client.patch(url, {"role": "member"}, format="json")
    assert demote.status_code == 409 and demote.data["error"]["code"] == "last_owner"
    assert owner.client.delete(url).status_code == 409
