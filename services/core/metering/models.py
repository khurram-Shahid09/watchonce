from django.db import models

from common.ids import PrefixedIdField
from common.models import TimeStampedModel
from common.tenancy import OrgOwnedModel


class LlmCall(OrgOwnedModel, TimeStampedModel):
    """One AI call: what it cost and how it ended (docs/09-data-model.md llm_calls)."""

    id = PrefixedIdField(prefix="llm")
    purpose = models.CharField(max_length=16)  # understand | sop | repair
    entity_id = models.CharField(max_length=32, blank=True)  # recording / run id
    provider = models.CharField(max_length=16)
    model = models.CharField(max_length=64)
    prompt_version = models.CharField(max_length=32, blank=True)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    cache_read_tokens = models.PositiveIntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    latency_ms = models.PositiveIntegerField(default=0)
    stop_reason = models.CharField(max_length=32, blank=True)
    error_code = models.CharField(max_length=32, blank=True)

    class Meta:
        db_table = "llm_calls"
        indexes = [models.Index(fields=["org", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.purpose} {self.provider}/{self.model} ${self.cost_usd}"
