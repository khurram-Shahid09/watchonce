import json

import pytest
from cryptography.exceptions import InvalidTag

from audit.models import AuditLog
from secrets_vault import crypto
from secrets_vault.models import Secret

pytestmark = pytest.mark.django_db

VALUES = {"username": "sara", "password": "acme-demo"}


def test_values_round_trip_and_never_appear_in_the_row(make_account) -> None:
    owner = make_account("sara@acme.test")
    response = owner.client.post(
        "/api/v1/secrets", {"name": "acme_login", "values": VALUES}, format="json"
    )
    assert response.status_code == 201, response.content
    assert response.data["fields"] == ["password", "username"]
    assert "values" not in response.data and "acme-demo" not in json.dumps(response.data)

    secret = Secret.objects.get()
    assert secret.values() == VALUES
    assert b"acme-demo" not in bytes(secret.ciphertext)
    assert b"acme-demo" not in bytes(secret.data_key_ciphertext)


def test_ciphertext_is_bound_to_its_row() -> None:
    sealed, key, _ = crypto.seal("sec_A", VALUES)
    assert crypto.unseal("sec_A", sealed, key) == VALUES
    with pytest.raises(InvalidTag):
        crypto.unseal("sec_B", sealed, key)  # copied onto another secret: useless


def test_listing_shows_names_only_and_members_cannot_manage(make_account) -> None:
    owner = make_account("sara@acme.test")
    member = make_account("imran@acme.test", org=owner.org, role="member")
    secret_id = owner.client.post(
        "/api/v1/secrets", {"name": "acme_login", "values": VALUES}, format="json"
    ).data["id"]

    listed = member.client.get("/api/v1/secrets").data
    assert listed == [{**listed[0], "name": "acme_login", "fields": ["password", "username"]}]
    assert "acme-demo" not in json.dumps(listed)
    assert (
        member.client.post(
            "/api/v1/secrets", {"name": "x", "values": {"a": "b"}}, format="json"
        ).status_code
        == 403
    )
    assert (
        member.client.put(
            f"/api/v1/secrets/{secret_id}", {"values": {"a": "b"}}, format="json"
        ).status_code
        == 403
    )
    assert member.client.delete(f"/api/v1/secrets/{secret_id}").status_code == 403


def test_rotate_delete_duplicates_and_audit(make_account) -> None:
    owner = make_account("sara@acme.test")
    url = "/api/v1/secrets"
    secret_id = owner.client.post(
        url, {"name": "acme_login", "values": VALUES}, format="json"
    ).data["id"]
    assert (
        owner.client.post(url, {"name": "acme_login", "values": VALUES}, format="json").status_code
        == 409
    )

    rotated = owner.client.put(
        f"{url}/{secret_id}",
        {"values": {"username": "sara", "password": "new-pass"}},
        format="json",
    )
    assert rotated.status_code == 200 and rotated.data["rotated_at"]
    assert Secret.objects.get().values()["password"] == "new-pass"
    assert owner.client.delete(f"{url}/{secret_id}").status_code == 204

    actions = list(AuditLog.objects.order_by("created_at").values_list("action", flat=True))
    assert actions[-3:] == ["secret.created", "secret.rotated", "secret.deleted"]
    assert "acme-demo" not in json.dumps(list(AuditLog.objects.values("metadata")))


@pytest.mark.parametrize(
    "body",
    [
        {"name": "Acme Login", "values": {"password": "x"}},
        {"name": "acme_login", "values": {}},
        {"name": "acme_login", "values": {"Pass Word": "x"}},
        {"name": "acme_login", "values": {"password": ""}},
    ],
)
def test_validation(make_account, body) -> None:
    owner = make_account("sara@acme.test")
    assert owner.client.post("/api/v1/secrets", body, format="json").status_code == 400


def test_secrets_are_invisible_to_other_workspaces(make_account) -> None:
    owner = make_account("sara@acme.test")
    other = make_account("x@other.test")
    secret_id = owner.client.post(
        "/api/v1/secrets", {"name": "acme_login", "values": VALUES}, format="json"
    ).data["id"]
    assert other.client.get("/api/v1/secrets").data == []
    assert other.client.get(f"/api/v1/secrets/{secret_id}").status_code == 404
    assert other.client.delete(f"/api/v1/secrets/{secret_id}").status_code == 404
