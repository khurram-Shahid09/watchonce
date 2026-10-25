"""End-to-end: run a compiled Acme workflow from the dashboard, approve the checkpoint live,
and check the invoice number comes back. A second run is rejected at the checkpoint.

Prereqs: API :8000, `pnpm dev:web` :3000, portal :3001, a run worker
(`uv run celery -A config worker -Q run --pool=solo -n run@%h`). Run from services/core:

    WATCHONCE_EMAIL=... WATCHONCE_PASSWORD=... WATCHONCE_WORKFLOW=wf_... \
      uv run --with playwright python -I ../../apps/web/e2e/run_workflow.py
"""

import os
import re
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

WEB = os.environ.get("WATCHONCE_WEB", "http://localhost:3000")
EMAIL = os.environ["WATCHONCE_EMAIL"]
PASSWORD = os.environ["WATCHONCE_PASSWORD"]
WORKFLOW = os.environ["WATCHONCE_WORKFLOW"]
SHOTS = Path(os.environ["SHOTS_DIR"]) if os.environ.get("SHOTS_DIR") else None

failures: list[str] = []


def check(ok: bool, message: str) -> None:
    print(("  ok   " if ok else "  FAIL ") + message)
    if not ok:
        failures.append(message)


def shot(page, name: str) -> None:
    if SHOTS:
        page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)


def start_run(page, description: str) -> str:
    page.goto(f"{WEB}/workflows/{WORKFLOW}?tab=run")
    page.get_by_role("button", name="Run now").wait_for()
    if page.get_by_text("missing").count():
        page.get_by_label("username").fill("sara")
        page.get_by_label("password").fill("acme-demo")
        page.get_by_role("button", name=re.compile("^Save ")).click()
        expect(page.get_by_text("✓ saved")).to_be_visible()
        check(True, "saved the Acme login from the run form")
    page.get_by_label("vendor name").fill("City Power & Light")
    page.get_by_label("amount").fill("432.1")
    page.get_by_label("due date").fill("2026-12-01")
    if page.get_by_label("description").count():
        page.get_by_label("description").fill(description)
    page.get_by_role("button", name="Run now").click()
    page.wait_for_url("**/runs/run_*", wait_until="commit")
    return page.url.rsplit("/", 1)[1]


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(f"{WEB}/login")
    page.get_by_label("Email").fill(EMAIL)
    page.get_by_label("Password").fill(PASSWORD)
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url("**/workflows", wait_until="commit")

    # --- Run 1: approve ---
    run_id = start_run(page, "Run by WatchOnce E2E (approved)")
    check(True, f"run {run_id} started")
    banner = page.get_by_text(re.compile("^Approval needed"))
    banner.wait_for(timeout=120_000)
    check(True, "the run paused at the checkpoint and the dashboard shows it live")
    frame_ok = page.evaluate("() => !!document.querySelector('img[alt=\"What the runner sees\"]')")
    check(frame_ok, "live browser frames are streaming")
    approval = page.locator("img[alt='Page waiting for approval']")
    approval.wait_for()
    page.wait_for_function("() => { const i = document.querySelector(\"img[alt='Page waiting for approval']\"); return i && i.complete && i.naturalWidth > 0 }")
    check(True, "the approval screenshot (with the highlighted button) loads")
    shot(page, "run-1-approval")
    page.get_by_role("button", name="Approve and continue").click()
    expect(page.get_by_text("Succeeded").first).to_be_visible(timeout=90_000)
    check(True, "approved run succeeded")
    page.reload()
    number = page.locator("dd.font-mono").first
    number.wait_for()
    check(bool(re.fullmatch(r"INV-\d+", number.inner_text().strip())), f"invoice number extracted: {number.inner_text().strip()}")
    check(page.get_by_text(re.compile("approved by")).count() == 1, "the approval is on the record with who approved it")
    shot(page, "run-1-done")

    # --- Run 2: reject ---
    run_id = start_run(page, "Run by WatchOnce E2E (rejected)")
    page.get_by_text(re.compile("^Approval needed")).wait_for(timeout=120_000)
    page.get_by_role("button", name="Reject (stop the run)").click()
    expect(page.get_by_text("Rejected").first).to_be_visible(timeout=60_000)
    check(True, f"rejected run {run_id} stopped before submitting")

    page.goto(f"{WEB}/runs")
    rows = page.locator("a[href^='/runs/run_']")
    rows.first.wait_for()
    check(rows.count() >= 2, "runs page lists the runs")
    browser.close()

print(f"\n{'PASSED' if not failures else f'{len(failures)} FAILED'}")
sys.exit(1 if failures else 0)
