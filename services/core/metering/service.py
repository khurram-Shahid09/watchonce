"""Cost logging and the per-workspace monthly AI budget (docs/06-ai-pipeline.md)."""

from decimal import Decimal

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from accounts.models import Organization
from engine.llm.types import Usage

from .models import LlmCall

# USD per million tokens: (input, output, cache read). Unknown models count as free and are
# logged with tokens only; free-tier Gemini in development really is free.
PRICES: dict[str, tuple[Decimal, Decimal, Decimal]] = {
    "claude-opus-5-5": (Decimal(4), Decimal(20), Decimal("0.20")),
    "claude-opus-5": (Decimal(5), Decimal(25), Decimal("0.50")),
    "claude-opus-4-8": (Decimal(5), Decimal(25), Decimal("0.50")),
    "claude-sonnet-5-5": (Decimal(2), Decimal(10), Decimal("0.20")),
}
MILLION = Decimal(1_000_000)


def cost_of(usage: Usage) -> Decimal:
    price = PRICES.get(usage.model)
    if price is None:
        return Decimal(0)
    inp, out, cached = price
    total = (
        Decimal(usage.input_tokens) * inp
        + Decimal(usage.output_tokens) * out
        + Decimal(usage.cache_read_tokens) * cached
    ) / MILLION
    return total.quantize(Decimal("0.0001"))


def record_call(
    *,
    org: Organization,
    purpose: str,
    usage: Usage,
    entity_id: str = "",
    prompt_version: str = "",
    error_code: str = "",
) -> LlmCall:
    return LlmCall.objects.create(
        org=org,
        purpose=purpose,
        entity_id=entity_id,
        provider=usage.provider,
        model=usage.model[:64],
        prompt_version=prompt_version,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_tokens=usage.cache_read_tokens,
        cost_usd=cost_of(usage),
        latency_ms=usage.latency_ms,
        stop_reason=usage.stop_reason[:32],
        error_code=error_code[:32],
    )


def month_spend(org: Organization) -> Decimal:
    start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total = LlmCall.objects.for_org(org).filter(created_at__gte=start).aggregate(s=Sum("cost_usd"))
    return total["s"] or Decimal(0)


def budget_left(org: Organization) -> bool:
    return month_spend(org) < Decimal(str(settings.LLM_MONTHLY_BUDGET_USD))
