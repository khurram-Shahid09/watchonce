from django.conf import settings
from django.db import models

from common.ids import PrefixedIdField
from common.models import TimeStampedModel
from common.tenancy import OrgOwnedModel


class Recording(OrgOwnedModel, TimeStampedModel):
    """One recorded task. Files live in object storage under ``storage_prefix``:
    ``events.json``, ``frames/NNNN.webp`` and, after normalization, ``candidates.json``."""

    class Status(models.TextChoices):
        UPLOADING = "uploading"
        UPLOADED = "uploaded"
        COMPILING = "compiling"
        COMPILED = "compiled"
        FAILED = "failed"

    id = PrefixedIdField(prefix="rec")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    description = models.TextField(max_length=1000)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.UPLOADING)
    storage_prefix = models.CharField(max_length=200)
    start_url = models.URLField(max_length=2000)
    event_count = models.PositiveIntegerField()
    frame_names = models.JSONField(default=list, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    candidate_count = models.PositiveIntegerField(null=True, blank=True)
    error = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "recordings"
        indexes = [models.Index(fields=["org", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.description[:40]} ({self.id})"

    def save(self, *args, **kwargs) -> None:
        if not self.storage_prefix:
            self.storage_prefix = f"org/{self.org_id}/rec/{self.id}/"
        super().save(*args, **kwargs)

    def key(self, name: str) -> str:
        return self.storage_prefix + name

    @property
    def frame_count(self) -> int:
        return len(self.frame_names)
