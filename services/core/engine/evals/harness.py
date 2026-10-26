"""Shared pieces of the evals: load a golden, compile it, replay a workflow version.

Everything runs in a throwaway workspace with in-memory storage, so an eval never touches
real workflows or the object store. Checkpoints are approved automatically.
"""

import contextlib
import json
import os
import re
import time
import zlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from django import db
from django.conf import settings

GOLDEN_DIR = Path(__file__).resolve().parents[4] / "evals" / "golden"
REPORT_DIR = GOLDEN_DIR.parent / "reports"
TEMPLATE = re.compile(r"\{\{\s*([a-zA-Z_][\w.]*)")


@dataclass
class Golden:
    id: str
    recording: dict[str, Any]
    expected: dict[str, Any]


def load_goldens(only: list[str] | None = None) -> list[Golden]:
    goldens = []
    for folder in sorted(p for p in GOLDEN_DIR.iterdir() if (p / "expected.json").exists()):
        if only and folder.name not in only:
            continue
        goldens.append(
            Golden(
                folder.name,
                json.loads((folder / "recording.json").read_text(encoding="utf-8")),
                json.loads((folder / "expected.json").read_text(encoding="utf-8")),
            )
        )
    return goldens


@contextlib.contextmanager
def eval_workspace(name: str, keep: bool = False) -> Iterator[Any]:
    """The eval org (one per eval kind, reused) on in-memory storage, emptied before and
    after unless ``keep``. The org itself stays: its audit entries are append-only."""
    from accounts.models import Organization
    from common import storage

    lock = _lock_workspace(name)
    old_backend = settings.STORAGE_BACKEND
    settings.STORAGE_BACKEND = "memory"
    storage.get_storage.cache_clear()
    org = Organization.objects.filter(name=name).first() or Organization.objects.create(name=name)
    _empty_org(org)
    try:
        yield org
    finally:
        settings.STORAGE_BACKEND = old_backend
        storage.get_storage.cache_clear()
        if not keep:
            _empty_org(org)
        lock.close()  # ends the session, which releases the lock


def _lock_workspace(name: str):
    """One eval per workspace at a time (it gets emptied). A connection of its own, since
    replays close Django's connections."""
    import psycopg

    cfg = settings.DATABASES["default"]
    conn = psycopg.connect(
        dbname=cfg["NAME"], user=cfg["USER"], password=cfg["PASSWORD"],
        host=cfg["HOST"] or "localhost", port=cfg["PORT"] or 5432, autocommit=True,
    )  # fmt: skip
    row = conn.execute("SELECT pg_try_advisory_lock(%s)", [zlib.crc32(name.encode())]).fetchone()
    if not row or not row[0]:
        conn.close()
        raise RuntimeError(f"Another eval is using the {name!r} workspace; wait for it to end.")
    return conn


def _empty_org(org) -> None:
    from metering.models import LlmCall
    from recordings.models import Recording
    from runs.models import Batch, Run
    from secrets_vault.models import Secret
    from workflows.models import Workflow

    # Runs and batches PROTECT their version; remove them before the workflows go.
    Run.objects.filter(org=org).delete()
    Batch.objects.filter(org=org).delete()
    Workflow.objects.filter(org=org).update(active_version=None)
    Workflow.objects.filter(org=org).delete()
    Recording.objects.filter(org=org).delete()
    Secret.objects.filter(org=org).delete()
    LlmCall.objects.filter(org=org).delete()


# --- compile ----------------------------------------------------------------------------


@dataclass
class Compiled:
    workflow: Any = None
    spec: dict[str, Any] = field(default_factory=dict)
    seconds: float = 0.0
    cost_usd: float = 0.0
    tokens: int = 0
    llm_ms: int = 0
    by: str = ""
    error: str = ""


def compile_golden(org, golden: Golden) -> Compiled:
    from common.storage import get_storage
    from engine.compiler.pipeline import compile_recording
    from metering.models import LlmCall
    from recordings.models import Recording

    data = golden.recording
    meta = data["recording"]
    recording = Recording.objects.create(
        org=org,
        description=meta["description"],
        start_url=meta["startUrl"],
        event_count=len(data["events"]),
        frame_names=list(data["frames"]),
        status=Recording.Status.UPLOADED,
    )
    storage = get_storage()
    events = {k: data[k] for k in ("format_version", "recording", "events")}
    storage.put_bytes(recording.key("events.json"), json.dumps(events).encode(), "application/json")
    for name, url in data["frames"].items():
        storage.put_bytes(recording.key(name), _data_url_bytes(url), "image/webp")

    result = Compiled()
    started = time.perf_counter()
    try:
        workflow = compile_recording(recording)
    except Exception as exc:  # CompileError, LLMError: an eval result, not a crash
        result.error = f"{getattr(exc, 'code', type(exc).__name__)}: {exc}"
        result.seconds = time.perf_counter() - started
        return result
    result.seconds = time.perf_counter() - started
    workflow.refresh_from_db()
    result.workflow = workflow
    result.spec = workflow.active_version.spec
    result.by = result.spec.get("source", {}).get("compiled_by", "")
    for call in LlmCall.objects.filter(org=org, entity_id=recording.id):
        result.cost_usd += float(call.cost_usd)
        result.tokens += call.input_tokens + call.output_tokens
        result.llm_ms += call.latency_ms
    return result


def _data_url_bytes(url: str) -> bytes:
    import base64

    return base64.b64decode(url.split(",", 1)[1])


# --- matching compiled steps to the answer key ------------------------------------------


def step_name(step: dict[str, Any]) -> str | None:
    """The element a step acts on, as a person would name it."""
    target = step.get("target", {})
    if target.get("fingerprint", {}).get("accessible_name"):
        return str(target["fingerprint"]["accessible_name"])
    locators = target.get("locators", [])
    for kinds in (("role",), ("label", "placeholder"), ("text",)):
        for loc in locators:
            if loc["kind"] in kinds:
                name = loc.get("name") if loc["kind"] == "role" else loc.get("value")
                if name:
                    return str(name)
    return None


def _same(expected: list, step: dict[str, Any]) -> bool:
    action, name = expected
    if action != step["action"]:
        return False
    if name is None:
        return True
    return _norm(name) == _norm(step_name(step) or "")


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def align(expected: list[list], steps: list[dict[str, Any]]) -> list[tuple[int, int]]:
    """Longest common subsequence of expected [action, name] pairs and compiled steps."""
    n, m = len(expected), len(steps)
    best = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            if _same(expected[i], steps[j]):
                best[i][j] = best[i + 1][j + 1] + 1
            else:
                best[i][j] = max(best[i + 1][j], best[i][j + 1])
    pairs, i, j = [], 0, 0
    while i < n and j < m:
        if _same(expected[i], steps[j]):
            pairs.append((i, j))
            i, j = i + 1, j + 1
        elif best[i + 1][j] >= best[i][j + 1]:
            i += 1
        else:
            j += 1
    return pairs


def template_refs(step: dict[str, Any]) -> list[str]:
    text = " ".join(str(step.get(k, "")) for k in ("value", "label", "url"))
    return TEMPLATE.findall(text)


def uses_input(step: dict[str, Any]) -> bool:
    return any(not ref.startswith(("secrets.", "outputs.")) for ref in template_refs(step))


# --- replay -----------------------------------------------------------------------------


class AutoApprove:
    """Stand-in for runs.live: approves every checkpoint, never cancels."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def publish(self, run_id: str, event: dict[str, Any]) -> None:
        self.events.append(event)

    def wait_for_decision(self, run_id: str, timeout_s: int) -> str | None:
        return "approve"

    def cancel_requested(self, run_id: str) -> bool:
        return False

    def clear(self, run_id: str) -> None:
        pass


def replay_inputs(spec: dict[str, Any], replay: dict[str, str]) -> dict[str, Any]:
    """Input values for a run: the answer key's replay value for the field an input fills,
    else the value seen in the recording."""
    by_input: dict[str, str] = {}
    for step in spec["steps"]:
        name = step_name(step)
        for ref in template_refs(step):
            if name in replay:
                by_input.setdefault(ref.split(".")[0], replay[name])
    inputs: dict[str, Any] = {}
    for spec_input in spec.get("inputs", []):
        value = by_input.get(spec_input["name"], spec_input.get("example"))
        if spec_input["type"] == "number" and value not in (None, ""):
            value = float(value)
        if value is not None:
            inputs[spec_input["name"]] = value
    return inputs


def save_logins(org, spec: dict[str, Any], login: dict[str, str]) -> None:
    from secrets_vault.models import Secret

    for secret in spec.get("secrets", []):
        values = {f: login.get(f, "") for f in secret["fields"]}
        obj = Secret.objects.filter(org=org, name=secret["name"]).first() or Secret(
            org=org, name=secret["name"]
        )
        obj.set_values(values)
        obj.save()


@dataclass
class Replay:
    status: str
    error: str = ""
    seconds: float = 0.0
    run: Any = None
    events: list[dict[str, Any]] = field(default_factory=list)


def replay(org, version, inputs: dict[str, Any], browsers: "Browsers") -> Replay:
    from engine.runner.executor import Executor
    from runs.models import Run

    run = Run.objects.create(
        org=org,
        workflow=version.workflow,
        version=version,
        triggered_by="eval",
        status=Run.Status.RUNNING,
        inputs=inputs,
    )
    live = AutoApprove()
    started = time.perf_counter()
    Executor(run, browsers.get(), live=live).execute()
    db.connections.close_all()  # Playwright's sync API runs Django on a second connection
    run.refresh_from_db()
    message = f"{run.error_code}: {run.error_message}" if run.error_code else ""
    return Replay(run.status, message, time.perf_counter() - started, run, live.events)


class Browsers:
    """Hands out a live Chromium, starting a new one if the last one died (a long eval
    shouldn't turn every later case into a crash)."""

    def __init__(self, playwright) -> None:
        self.playwright = playwright
        self.browser = None

    def get(self):
        if self.browser is None or not self.browser.is_connected():
            self.browser = self.playwright.chromium.launch(headless=True)
        return self.browser


@contextlib.contextmanager
def chromium() -> Iterator[Browsers]:
    from playwright.sync_api import sync_playwright

    os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")  # as engine/runner/browser.py
    with sync_playwright() as p:
        browsers = Browsers(p)
        try:
            yield browsers
        finally:
            if browsers.browser is not None and browsers.browser.is_connected():
                browsers.browser.close()
            db.connections.close_all()


def set_portal_variant(variant: str, portal: str = "http://localhost:3001") -> None:
    import httpx

    headers = {"x-admin-token": os.environ.get("ACME_ADMIN_TOKEN", "")}
    response = httpx.put(f"{portal}/api/variant", json={"variant": variant}, headers=headers)
    response.raise_for_status()
