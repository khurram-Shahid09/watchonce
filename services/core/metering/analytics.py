"""Workspace analytics: what the automations did and what they saved (docs/10-api-spec.md)."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

RANGES = {"7d": 7, "30d": 30, "90d": 90}


def summary(org, days: int) -> dict[str, Any]:
    from runs.models import HealEvent, Run
    from workflows.models import Workflow

    from .models import LlmCall

    since = timezone.now() - timedelta(days=days)
    runs = Run.objects.filter(org=org, created_at__gte=since)
    counts = runs.aggregate(
        total=Count("id"),
        succeeded=Count("id", filter=Q(status=Run.Status.SUCCEEDED)),
        finished=Count("id", filter=Q(status__in=Run.FINISHED)),
    )

    per_workflow = {
        row["workflow_id"]: row
        for row in runs.values("workflow_id").annotate(
            runs=Count("id"), succeeded=Count("id", filter=Q(status=Run.Status.SUCCEEDED))
        )
    }
    workflows = []
    saved_sec = 0
    for wf in Workflow.objects.for_org(org).filter(pk__in=per_workflow).order_by("name"):
        row = per_workflow[wf.pk]
        saved = (wf.manual_duration_sec or 0) * row["succeeded"]
        saved_sec += saved
        workflows.append(
            {
                "workflow_id": wf.pk,
                "name": wf.name,
                "runs": row["runs"],
                "succeeded": row["succeeded"],
                "manual_duration_sec": wf.manual_duration_sec,
                "hours_saved": round(saved / 3600, 2),
            }
        )
    workflows.sort(key=lambda w: (-w["hours_saved"], -w["runs"]))

    by_day = {
        row["day"]: row
        for row in runs.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(runs=Count("id"), succeeded=Count("id", filter=Q(status=Run.Status.SUCCEEDED)))
    }
    today = timezone.localdate()
    daily = []
    for offset in range(days - 1, -1, -1):
        day: date = today - timedelta(days=offset)
        counted: dict[str, Any] = dict(by_day.get(day) or {})
        daily.append(
            {"date": day, "runs": counted.get("runs", 0), "succeeded": counted.get("succeeded", 0)}
        )

    heals = HealEvent.objects.filter(org=org, created_at__gte=since).aggregate(
        total=Count("id"),
        approved=Count(
            "id",
            filter=Q(decision__in=[HealEvent.Decision.APPROVED, HealEvent.Decision.AUTO]),
        ),
        pending=Count("id", filter=Q(decision=HealEvent.Decision.PENDING)),
    )
    spend = LlmCall.objects.filter(org=org, created_at__gte=since).aggregate(s=Sum("cost_usd"))[
        "s"
    ] or Decimal(0)

    return {
        "range_days": days,
        "since": since,
        "runs": counts["total"],
        "succeeded": counts["succeeded"],
        "success_rate": counts["succeeded"] / counts["finished"] if counts["finished"] else None,
        "hours_saved": round(saved_sec / 3600, 2),
        "workflows_without_duration": sum(
            1 for w in workflows if not w["manual_duration_sec"] and w["succeeded"]
        ),
        "heals": heals["total"],
        "heals_approved": heals["approved"],
        "heals_pending": heals["pending"],
        "llm_spend_usd": spend,
        "workflows": workflows,
        "daily": daily,
    }
