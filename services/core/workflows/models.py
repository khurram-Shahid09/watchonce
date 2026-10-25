from django.conf import settings
from django.db import models

from common.ids import PrefixedIdField
from common.models import TimeStampedModel
from common.tenancy import OrgOwnedModel


class Workflow(OrgOwnedModel, TimeStampedModel):
    id = PrefixedIdField(prefix="wf")
    name = models.CharField(max_length=200)
    description = models.TextField(max_length=2000, blank=True)
    recording = models.OneToOneField(
        "recordings.Recording",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workflow",
    )
    active_version = models.ForeignKey(
        "WorkflowVersion", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    manual_duration_sec = models.PositiveIntegerField(null=True, blank=True)  # hours saved
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "workflows"
        indexes = [models.Index(fields=["org", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.id})"


class WorkflowVersion(OrgOwnedModel, TimeStampedModel):
    """Immutable once saved: every edit or heal creates the next version (docs/05)."""

    class Status(models.TextChoices):
        DRAFT = "draft"
        ACTIVE = "active"
        PENDING_HEAL = "pending_heal"
        ARCHIVED = "archived"

    id = PrefixedIdField(prefix="wfv")
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name="versions")
    version = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    spec = models.JSONField()
    spec_hash = models.CharField(max_length=64)
    sop_markdown = models.TextField(blank=True)
    warnings = models.JSONField(default=list, blank=True)  # validator + compiler warnings
    created_by = models.CharField(max_length=64)  # user:{id} | compiler | healer
    parent_version = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    change_note = models.CharField(max_length=500, blank=True)
    compile_info = models.JSONField(default=dict, blank=True)  # provider, model, prompts

    class Meta:
        db_table = "workflow_versions"
        constraints = [
            models.UniqueConstraint(fields=["workflow", "version"], name="uniq_workflow_version")
        ]
        indexes = [models.Index(fields=["workflow", "status"])]

    def __str__(self) -> str:
        return f"{self.workflow_id} v{self.version} ({self.status})"
