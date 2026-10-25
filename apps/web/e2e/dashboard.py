"""End-to-end: the dashboard against a running API with at least one compiled workflow.

Prereqs: API on :8000, `pnpm dev:web` on :3000, an account with a compiled workflow.
Run from services/core (it has Playwright available):

    WATCHONCE_EMAIL=... WATCHONCE_PASSWORD=... \
      uv run --with playwright python -I ../../apps/web/e2e/dashboard.py
"""

import os
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

WEB = os.environ.get("WATCHONCE_WEB", "http://localhost:3000")
EMAIL = os.environ["WATCHONCE_EMAIL"]
PASSWORD = os.environ["WATCHONCE_PASSWORD"]
SHOTS = Path(os.environ.get("SHOTS_DIR", ".")) if os.environ.get("SHOTS_DIR") else None

failures: list[str] = []


def check(ok: bool, message: str) -> None:
    print(("  ok   " if ok else "  FAIL ") + message)
    if not ok:
        failures.append(message)


def shot(page, name: str) -> None:
    if SHOTS:
        page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)


with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()

    page.goto(f"{WEB}/workflows")
    check("/login" in page.url, "signed-out visitors are sent to /login")
    page.get_by_label("Email").fill(EMAIL)
    page.get_by_label("Password").fill("wrong-password")
    page.get_by_role("button", name="Sign in").click()
    # (Next.js also renders an empty role="alert" route announcer; match the message.)
    expect(page.get_by_role("alert").filter(has_text="Invalid email or password")).to_be_visible()
    check(True, "a wrong password shows an error")

    page.get_by_label("Password").fill(PASSWORD)
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url("**/workflows", wait_until="commit")
    cookies = {c["name"]: c for c in ctx.cookies()}
    check({"wo_access", "wo_refresh"} <= set(cookies), "session cookies set on the dashboard origin")
    check(all(cookies[n]["httpOnly"] for n in ("wo_access", "wo_refresh")), "session cookies are httpOnly")
    check(not page.evaluate("document.cookie").strip(), "no token is readable from page scripts")
    shot(page, "1-workflows")

    cards = page.locator("a[href^='/workflows/wf_']")
    cards.first.wait_for()  # the list streams in after the page shell
    check(cards.count() >= 1, f"workflow list shows workflows ({cards.count()})")
    cards.first.click()
    page.wait_for_url("**/workflows/wf_*", wait_until="commit")
    workflow_url = page.url.split("?")[0]
    expect(page.get_by_role("heading", level=1)).to_be_visible()

    steps = page.locator("main ol.space-y-3 > li")
    steps.first.wait_for()
    check(steps.count() >= 5, f"steps tab lists steps ({steps.count()})")
    check(page.get_by_text("Needs approval").count() >= 1, "the submit step is marked as needing approval")
    images = page.locator("ol img")
    images.first.scroll_into_view_if_needed()
    page.wait_for_function("() => [...document.querySelectorAll('ol img')].slice(0, 3).every(i => i.complete)")
    loaded = page.evaluate("() => [...document.querySelectorAll('ol img')].slice(0, 3).map(i => i.naturalWidth)")
    check(all(w > 100 for w in loaded), f"screenshots load through the dashboard ({loaded})")
    shot(page, "2-steps")

    page.get_by_role("link", name="SOP").click()
    page.wait_for_url("**tab=sop**", wait_until="commit")
    check(page.locator("article.sop h1").count() == 1, "SOP renders as a document")
    sop_imgs = page.evaluate("() => [...document.querySelectorAll('article.sop img')].map(i => i.getAttribute('src'))")
    check(bool(sop_imgs) and all(s.startswith("/bff/") for s in sop_imgs), "SOP screenshots resolve to dashboard URLs")
    shot(page, "3-sop")

    page.get_by_role("link", name="Edit").click()
    page.wait_for_url("**tab=edit**", wait_until="commit")
    first_intent = page.get_by_label("Step 2 intent")
    original = first_intent.input_value()
    first_intent.fill(original + " (edited by E2E)")
    page.get_by_placeholder("What changed? (optional)").fill("E2E edit")
    page.get_by_role("button", name="Save as new version").click()
    page.wait_for_url("**?v=*", wait_until="commit")
    new_version = int(page.url.rsplit("v=", 1)[1].split("&")[0])
    check(page.get_by_text(original + " (edited by E2E)").count() >= 1, f"saved as version {new_version} and shown")
    shot(page, "4-saved")

    page.get_by_role("link", name="Versions").click()
    check(page.get_by_text(f"Version {new_version}").count() >= 1, "new version listed")

    # A spec that fails validation shows the validator's errors.
    page.goto(f"{workflow_url}?tab=edit&v={new_version}")
    page.get_by_label("Step 1 intent").fill("")
    page.get_by_role("button", name="Save as new version").click()
    expect(page.get_by_role("alert").filter(has_text="Step 1")).to_be_visible()
    check(True, "invalid edits are rejected with the step named")

    page.goto(f"{workflow_url}?tab=versions")
    page.get_by_role("button", name="Sign out").click()
    page.wait_for_url("**/login", wait_until="commit")
    check("wo_refresh" not in {c["name"] for c in ctx.cookies()}, "sign out clears the session")
    page.goto(workflow_url)
    check("/login" in page.url, "after sign out the workflow needs a new sign-in")
    browser.close()

print(f"\n{'PASSED' if not failures else f'{len(failures)} FAILED'}")
sys.exit(1 if failures else 0)
