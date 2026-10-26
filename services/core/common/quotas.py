"""Per-workspace hourly limits on work that costs money (docs/10-api-spec.md "Rate limits").

Counted from what was actually started in the last hour (audit entries and runs), not from
requests, so idempotent retries of the same call never use up the quota.
"""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from common.exceptions import ApiError

COMPILE_ACTIONS = ("recording.uploaded", "recording.recompile")


def _hour_ago():
    return timezone.now() - timedelta(hours=1)


def check_compiles(org) -> None:
    from audit.models import AuditLog

    used = AuditLog.objects.filter(
        org=org, action__in=COMPILE_ACTIONS, created_at__gte=_hour_ago()
    ).count()
    _check(used, 1, settings.ORG_COMPILES_PER_HOUR, "compiles")


def check_runs(org, count: int = 1) -> None:
    from runs.models import Run

    used = Run.objects.filter(org=org, created_at__gte=_hour_ago()).count()
    _check(used, count, settings.ORG_RUNS_PER_HOUR, "runs")


def _check(used: int, wanted: int, limit: int, what: str) -> None:
    if used + wanted > limit:
        raise ApiError(
            "rate_limited",
            f"This workspace can start {limit} {what} per hour; "
            f"{max(limit - used, 0)} left right now. Try again later.",
            status_code=429,
            details={"limit": limit, "used": used, "requested": wanted},
        )
