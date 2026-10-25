"""End-to-end self-healing: a workflow recorded on the original Acme portal runs against
"Portal v2" (ids renamed, classes hashed, labels changed, wrappers added, test ids removed).

The run heals the broken steps, an owner approves the fix in the Heals tab, and the next
run on v2 needs no healing. The portal is switched back to the original layout at the end.

Prereqs as in run_workflow.py. Run from services/core:

    WATCHONCE_EMAIL=... WATCHONCE_PASSWORD=... WATCHONCE_WORKFLOW=wf_... \
      uv run --with playwright python -I ../../apps/web/e2e/heal_workflow.py
"""

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

WEB = os.environ.get("WATCHONCE_WEB", "http://localhost:3000")
PORTAL = os.environ.get("ACME_PORTAL", "http://localhost:3001")
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


def set_variant(variant: str) -> None:
    req = urllib.request.Request(
        f"{PORTAL}/api/variant",
        data=json.dumps({"variant": variant}).encode(),
        method="PUT",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310 - local portal
        print(f"  portal layout -> {json.loads(r.read())['variant']}")


def run_once(page, label: str) -> str:
    page.goto(f"{WEB}/workflows/{WORKFLOW}?tab=run")
    page.get_by_role("button", name="Run now").click()
    page.wait_for_url("**/runs/run_*", wait_until="commit")
    page.get_by_text(re.compile("^Approval needed")).wait_for(timeout=180_000)
    shot(page, f"heal-{label}-approval")
    page.get_by_role("button", name="Approve and continue").click()
    page.get_by_text(re.compile("^(Succeeded|Failed)$")).first.wait_for(timeout=120_000)
    page.reload()
    page.locator("main ol li").first.wait_for()
    shot(page, f"heal-{label}-done")
    return page.url.rsplit("/", 1)[1]


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(f"{WEB}/login")
    page.get_by_label("Email").fill(EMAIL)
    page.get_by_label("Password").fill(PASSWORD)
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url("**/workflows", wait_until="commit")

    set_variant("v2")
    try:
        run_id = run_once(page, "1")
        status = page.locator("main span.rounded-full").first.inner_text()
        healed = page.get_by_text("self-healed", exact=True).count()
        check(status == "Succeeded", f"run {run_id} on Portal v2: {status}")
        check(healed >= 1, f"{healed} step(s) self-healed during the run")

        page.goto(f"{WEB}/workflows/{WORKFLOW}?tab=heals")
        pending = page.get_by_role("button", name=re.compile("^Approve (fix|all)"))
        pending.first.wait_for()
        check(page.get_by_text("When recorded").count() >= 1, "Heals tab shows before/after screenshots")
        shot(page, "heal-review")
        pending.first.click()
        expect(page.get_by_role("button", name=re.compile("^Approve (fix|all)"))).to_have_count(0, timeout=15_000)
        check(True, "owner approved the fix; it is the active version now")

        page.goto(f"{WEB}/workflows/{WORKFLOW}?tab=versions")
        check(page.get_by_text("Self-healing").count() >= 1, "the healed version is in the history")

        run_id = run_once(page, "2")
        status = page.locator("main span.rounded-full").first.inner_text()
        healed = page.get_by_text("self-healed", exact=True).count()
        check(status == "Succeeded" and healed == 0, f"second run {run_id} on v2: {status}, {healed} heals needed")
    finally:
        set_variant("original")
    browser.close()

print(f"\n{'PASSED' if not failures else f'{len(failures)} FAILED'}")
sys.exit(1 if failures else 0)
