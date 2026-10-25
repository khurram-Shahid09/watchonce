"""Redis plumbing shared by the API and the runner (docs/08 "Live view", "Checkpoints").

- ``run:{id}:events``   pub/sub channel: step / checkpoint / frame / done events (JSON)
- ``run:{id}:frame``    the latest live frame, so a viewer who joins late sees the page
- ``run:{id}:decision`` list the runner BLPOPs at a checkpoint: "approve" | "reject" | "cancel"
- ``run:{id}:cancel``   flag the runner checks between steps
"""

import json
from functools import cache
from typing import Any, cast

import redis
from django.conf import settings

KEY_TTL = 24 * 60 * 60


@cache
def client() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL)


def events_channel(run_id: str) -> str:
    return f"run:{run_id}:events"


def publish(run_id: str, event: dict[str, Any]) -> None:
    if event.get("type") == "frame":
        client().set(f"run:{run_id}:frame", json.dumps(event), ex=KEY_TTL)
    client().publish(events_channel(run_id), json.dumps(event))


def last_frame(run_id: str) -> dict[str, Any] | None:
    raw = cast(bytes | None, client().get(f"run:{run_id}:frame"))
    return json.loads(raw) if raw else None


def send_decision(run_id: str, decision: str) -> None:
    key = f"run:{run_id}:decision"
    client().rpush(key, decision)
    client().expire(key, KEY_TTL)


def wait_for_decision(run_id: str, timeout_s: int) -> str | None:
    """Block until a decision arrives; None on timeout."""
    item = cast(list[bytes] | None, client().blpop([f"run:{run_id}:decision"], timeout=timeout_s))
    return item[1].decode() if item else None


def request_cancel(run_id: str) -> None:
    client().set(f"run:{run_id}:cancel", "1", ex=KEY_TTL)
    send_decision(run_id, "cancel")  # wakes a runner waiting at a checkpoint


def cancel_requested(run_id: str) -> bool:
    return bool(client().exists(f"run:{run_id}:cancel"))


def clear(run_id: str) -> None:
    client().delete(f"run:{run_id}:decision", f"run:{run_id}:cancel")
