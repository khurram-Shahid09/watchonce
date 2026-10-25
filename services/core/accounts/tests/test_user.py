import pytest
from django.db import IntegrityError

from accounts.models import User

pytestmark = pytest.mark.django_db


def test_create_user_normalizes_email_and_hashes_password() -> None:
    user = User.objects.create_user("Sara@Example.COM", "correct horse battery")
    assert user.email == "sara@example.com"
    assert user.id.startswith("usr_")
    assert user.password != "correct horse battery"
    assert user.check_password("correct horse battery")
    assert not user.is_staff


def test_email_is_case_insensitively_unique() -> None:
    User.objects.create_user("imran@example.com", "pw-1234567890")
    with pytest.raises(IntegrityError):
        User.objects.create_user("IMRAN@example.com", "pw-1234567890")


def test_oauth_only_user_has_unusable_password() -> None:
    user = User.objects.create_user("oauth@example.com", google_sub="1234")
    assert not user.has_usable_password()


def test_create_superuser() -> None:
    admin = User.objects.create_superuser("admin@example.com", "pw-1234567890")
    assert admin.is_staff and admin.is_superuser
