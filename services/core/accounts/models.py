import hashlib
import secrets

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models

from common.ids import PrefixedIdField
from common.models import TimeStampedModel
from common.tenancy import OrgOwnedModel


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def _create(self, email: str, password: str | None, **extra) -> "User":
        if not email:
            raise ValueError("email is required")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()  # Google sign-in only
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra) -> "User":
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra) -> "User":
        extra["is_staff"] = True
        extra["is_superuser"] = True
        return self._create(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    """One account for the dashboard and the extension. Email is the login (case-insensitive)."""

    id = PrefixedIdField(prefix="usr")
    email = models.EmailField(max_length=254, unique=True)  # always stored lowercased
    name = models.CharField(max_length=200, blank=True)
    google_sub = models.CharField(max_length=255, null=True, blank=True, unique=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)  # Django admin access only

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        db_table = "users"

    def __str__(self) -> str:
        return self.email

    def save(self, *args, **kwargs) -> None:
        self.email = self.email.lower()
        super().save(*args, **kwargs)


class Organization(TimeStampedModel):
    """A workspace. Every tenant-owned row belongs to exactly one organization."""

    class Plan(models.TextChoices):
        FREE = "free"
        PRO = "pro"
        ENTERPRISE = "enterprise"

    id = PrefixedIdField(prefix="org")
    name = models.CharField(max_length=120)
    plan = models.CharField(max_length=20, choices=Plan.choices, default=Plan.FREE)
    settings = models.JSONField(default=dict, blank=True)  # default heal policy, retention days

    class Meta:
        db_table = "organizations"

    def __str__(self) -> str:
        return self.name


class Membership(OrgOwnedModel, TimeStampedModel):
    class Role(models.TextChoices):
        OWNER = "owner"  # approve heals, manage secrets/members, view audit
        MEMBER = "member"  # record, run, approve checkpoints on own runs

    id = PrefixedIdField(prefix="mem")
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)

    class Meta:
        db_table = "memberships"
        constraints = [
            models.UniqueConstraint(fields=["org", "user"], name="memberships_org_user_unique")
        ]

    def __str__(self) -> str:
        return f"{self.user_id} in {self.org_id} ({self.role})"

    @property
    def is_owner(self) -> bool:
        return self.role == self.Role.OWNER


class ApiToken(OrgOwnedModel, TimeStampedModel):
    """Personal access token (extension / API). Only the SHA-256 of the token is stored."""

    PREFIX = "pat_"
    plaintext = ""  # set on the instance returned by issue(); never stored

    id = PrefixedIdField(prefix="tok")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="api_tokens")
    name = models.CharField(max_length=100)
    token_hash = models.CharField(max_length=64, unique=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "api_tokens"

    def __str__(self) -> str:
        return f"{self.name} ({self.id})"

    @staticmethod
    def hash(raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()

    @classmethod
    def issue(
        cls, *, org: Organization, user: User, name: str, expires_at=None
    ) -> tuple["ApiToken", str]:
        """Create a token and return it with the plaintext, which is never retrievable again."""
        raw = cls.PREFIX + secrets.token_urlsafe(32)
        token = cls.objects.create(
            org=org, user=user, name=name, token_hash=cls.hash(raw), expires_at=expires_at
        )
        token.plaintext = raw
        return token, raw

    def is_usable(self, now) -> bool:
        return self.revoked_at is None and (self.expires_at is None or self.expires_at > now)
