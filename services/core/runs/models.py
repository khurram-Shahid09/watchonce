from django.conf import settings
from django.db import models

from common.ids import PrefixedIdField
from common.models import TimeStampedModel
from common.tenancy import OrgOwnedModel


class Batch(OrgOwnedModel, TimeStampedModel):
    """Many runs of one workflow version from a CSV, executed one after another
    (docs/08 "Batch runs")."""

    class Status(models.TextChoices):
        QUEUED = "queued"
        RUNNING = "running"
        FINISHED = "finished"  # every row ran (check the counts for failures)
        CANCELLED = "cancelled"

    id = PrefixedIdField(prefix="bat")
    workflow = models.ForeignKey(
        "workflows.Workflow", on_delete=models.CASCADE, related_name="batches"
    )
    version = models.ForeignKey(
        "workflows.WorkflowVersion", on_delete=models.PROTECT, related_name="+"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED)
    file_name = models.CharField(max_length=200, blank=True)
    columns = models.JSONField(default=list)  # CSV header, in order
    rows = models.JSONField(default=list)  # the raw CSV rows (dicts), for the results file
    column_map = models.JSONField(default=dict)  # input name -> CSV column
    total = models.PositiveIntegerField(default=0)
    succeeded = models.PositiveIntegerField(default=0)
    failed = models.PositiveIntegerField(default=0)
    approve_all = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "batches"

    def __str__(self) -> str:
        return f"{self.id} ({self.status} {self.succeeded}+{self.failed}/{self.total})"


class Run(OrgOwnedModel, TimeStampedModel):
    """One execution of a pinned workflow version (docs/08-runner-and-self-healing.md)."""

    class Status(models.TextChoices):
        QUEUED = "queued"
        RUNNING = "running"
        AWAITING_APPROVAL = "awaiting_approval"
        SUCCEEDED = "succeeded"
        FAILED = "failed"
        REJECTED = "rejected"
        CANCELLED = "cancelled"
        TIMED_OUT = "timed_out"

    FINISHED = frozenset({"succeeded", "failed", "rejected", "cancelled", "timed_out"})

    id = PrefixedIdField(prefix="run")
    workflow = models.ForeignKey(
        "workflows.Workflow", on_delete=models.CASCADE, related_name="runs"
    )
    version = models.ForeignKey(
        "workflows.WorkflowVersion", on_delete=models.PROTECT, related_name="+"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    triggered_by = models.CharField(max_length=64)  # user:{id} | batch | api
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    inputs = models.JSONField(default=dict)  # never secrets
    outputs = models.JSONField(default=dict)
    current_step_id = models.CharField(max_length=16, blank=True)
    error_code = models.CharField(max_length=32, blank=True)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    artifacts_prefix = models.CharField(max_length=200, blank=True)
    llm_cost_usd = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    batch = models.ForeignKey(
        Batch, on_delete=models.CASCADE, null=True, blank=True, related_name="runs"
    )
    row_index = models.PositiveIntegerField(null=True, blank=True)  # 1-based CSV row

    class Meta:
        db_table = "runs"
        indexes = [
            models.Index(fields=["org", "workflow", "-created_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"{self.id} ({self.status})"

    def save(self, *args, **kwargs) -> None:
        if not self.artifacts_prefix:
            self.artifacts_prefix = f"org/{self.org_id}/runs/{self.id}/"
        super().save(*args, **kwargs)

    @property
    def finished(self) -> bool:
        return self.status in self.FINISHED


class RunStep(OrgOwnedModel, TimeStampedModel):
    class Status(models.TextChoices):
        RUNNING = "running"
        OK = "ok"
        HEALED = "healed"
        FAILED = "failed"
        SKIPPED = "skipped"
        AWAITING_APPROVAL = "awaiting_approval"

    id = PrefixedIdField(prefix="rst")
    run = models.ForeignKey(Run, on_delete=models.CASCADE, related_name="steps")
    step_id = models.CharField(max_length=16)
    seq = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING)
    locator_used = models.JSONField(null=True, blank=True)
    rung = models.CharField(max_length=4, blank=True)  # L0 primary locator, L1 fallback
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    screenshot_ref = models.CharField(max_length=64, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        db_table = "run_steps"
        constraints = [models.UniqueConstraint(fields=["run", "seq"], name="uniq_run_step_seq")]
        ordering = ["seq"]

    def __str__(self) -> str:
        return f"{self.run_id} {self.step_id} ({self.status})"


class CheckpointDecision(OrgOwnedModel, TimeStampedModel):
    class Decision(models.TextChoices):
        APPROVE = "approve"
        REJECT = "reject"

    id = PrefixedIdField(prefix="ckd")
    run = models.ForeignKey(Run, on_delete=models.CASCADE, related_name="decisions")
    step_id = models.CharField(max_length=16)
    decision = models.CharField(max_length=8, choices=Decision.choices)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    note = models.CharField(max_length=500, blank=True)
    screenshot_ref = models.CharField(max_length=64, blank=True)

    class Meta:
        db_table = "checkpoint_decisions"
        constraints = [
            models.UniqueConstraint(fields=["run", "step_id"], name="uniq_checkpoint_decision")
        ]

    def __str__(self) -> str:
        return f"{self.run_id} {self.step_id}: {self.decision}"


class HealEvent(OrgOwnedModel, TimeStampedModel):
    """A step the runner found again after the page changed (docs/08 "Persisting a heal")."""

    class Decision(models.TextChoices):
        PENDING = "pending"
        APPROVED = "approved"
        REJECTED = "rejected"
        AUTO = "auto"  # activated by heal_policy=auto

    id = PrefixedIdField(prefix="hel")
    run = models.ForeignKey(Run, on_delete=models.CASCADE, related_name="heals")
    workflow = models.ForeignKey(
        "workflows.Workflow", on_delete=models.CASCADE, related_name="heals"
    )
    step_id = models.CharField(max_length=16)
    rung = models.CharField(max_length=4)  # L2 fingerprint | L3 AI
    before_locators = models.JSONField(default=list)
    after_locators = models.JSONField(default=list)
    score = models.FloatField()
    model_confidence = models.FloatField(null=True, blank=True)
    explanation = models.TextField()
    before_image_ref = models.CharField(max_length=64, blank=True)  # recording frame
    after_image_ref = models.CharField(max_length=64, blank=True)  # run artifact
    resulting_version = models.ForeignKey(
        "workflows.WorkflowVersion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    decision = models.CharField(max_length=10, choices=Decision.choices, default=Decision.PENDING)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=4, default=0)

    class Meta:
        db_table = "heal_events"
        indexes = [models.Index(fields=["workflow", "decision"])]

    def __str__(self) -> str:
        return f"{self.run_id} {self.step_id} {self.rung} ({self.decision})"
