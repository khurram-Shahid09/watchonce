from django.conf import settings
from django.db import models

from common.ids import PrefixedIdField
from common.models import TimeStampedModel
from common.tenancy import OrgOwnedModel


class AuthoringSession(OrgOwnedModel, TimeStampedModel):
    """The agent building a workflow from plain instructions (docs/17-authoring-agent.md):
    a new workflow, or a new version of one whose run failed ("fix")."""

    class Status(models.TextChoices):
        QUEUED = "queued"
        RUNNING = "running"
        AWAITING_APPROVAL = "awaiting_approval"
        SUCCEEDED = "succeeded"
        FAILED = "failed"
        CANCELLED = "cancelled"
        TIMED_OUT = "timed_out"

    class Mode(models.TextChoices):
        CREATE = "create"
        FIX = "fix"

    FINISHED = frozenset({"succeeded", "failed", "cancelled", "timed_out"})

    id = PrefixedIdField(prefix="aut")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.CREATE)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    start_url = models.URLField(max_length=2000)
    instructions = models.TextField(max_length=8000)
    # fix mode: the version that failed and the run it failed in
    base_version = models.ForeignKey(
        "workflows.WorkflowVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    source_run = models.ForeignKey(
        "runs.Run", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # what the agent did, for the live view and the record: n, intent, action, status, error
    steps = models.JSONField(default=list)
    question = models.JSONField(default=dict)  # the approval it is waiting for, if any
    workflow = models.ForeignKey(
        "workflows.Workflow", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    version = models.ForeignKey(
        "workflows.WorkflowVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    error_code = models.CharField(max_length=32, blank=True)
    error_message = models.TextField(blank=True)  # on success: a note for the user, or ""
    llm_cost_usd = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "authoring_sessions"
        indexes = [models.Index(fields=["org", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.id} ({self.status})"

    @property
    def finished(self) -> bool:
        return self.status in self.FINISHED
