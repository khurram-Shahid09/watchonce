"""Scenes for the authoring-agent clip (docs/17-authoring-agent.md).

20-agent: describe a task -> the agent builds it live (one real AI session, about 10-15
          calls) -> approval before Submit -> saved workflow -> its steps.
21-fix:   a failed run (a vendor that isn't in the portal; no AI) -> "Fix this workflow".

Outputs: demo/out/raw/20-agent.webm + 20-agent-marks.json, demo/out/raw/21-fix.webm, and
stills in demo/out/shots/agent-*.png. Then demo/scripts/make_agent_video.py cuts the clip.

    cd services/core
    uv run --with playwright python -I ../../demo/scripts/capture_agent.py
    DEMO_AGENT=offline uv run ...   # with the run worker on LLM_PROVIDER_AUTHOR=fake (no AI)
"""

import json
import os
import shutil
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from capture_scenes import (  # noqa: E402
    CURSOR_JS,
    EMAIL,
    PASSWORD,
    PORTAL,
    RAW,
    SHOTS,
    SIZE,
    WEB,
    beat,
    glide_click,
    set_variant,
    sign_in,
    snap,
    type_into,
    workflows,
)

API = "http://localhost:8000/api/v1"
# With Gemini or Claude, free-form instructions work. The offline agent (run worker started with
# LLM_PROVIDER_AUTHOR=fake, no AI calls) needs one action per line: DEMO_AGENT=offline.
INSTRUCTIONS = {
    "ai": """Log in with my saved login localhost_login
Create a new invoice for Northwind Ltd: amount 980.50, due date 12/01/2026, description PO-5512 Desk lamps
Submit it for approval
Read the new invoice number as invoice_number""",
    "offline": """Task: Enter a vendor invoice and submit it for approval
Log in with my saved login localhost_login
Click Invoices
Click New invoice
Select Northwind Ltd in Vendor
Type 980.50 in Amount
Type 12/01/2026 in Due date
Type PO-5512 Desk lamps in Description
Click Submit
Wait for Invoice created
Read Status as invoice_status""",
}[os.environ.get("DEMO_AGENT", "ai")]
HINT = "If the vendor isn't in the list, choose Northwind Ltd and put the vendor's name in the description."


def api(path: str, body: dict | None = None, token: str = "") -> dict:
    req = urllib.request.Request(  # noqa: S310 - the local API
        API + path, data=json.dumps(body).encode() if body is not None else None,
        method="POST" if body is not None else "GET",
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})},
    )  # fmt: skip
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 - local API
        return json.loads(r.read())


def failed_run(token: str, workflow_id: str) -> str:
    """A run that fails cleanly (no AI): the vendor isn't one the portal offers."""
    run = api(
        f"/workflows/{workflow_id}/runs",
        {"inputs": {"vendor": "Globex Unknown Ltd", "amount": "310", "due_date": "2026-12-05",
                    "description": "Monthly cleaning"}},
        token,
    )  # fmt: skip
    for _ in range(90):
        time.sleep(2)
        state = api(f"/runs/{run['id']}", token=token)
        if state["status"] in ("failed", "succeeded", "cancelled", "timed_out", "rejected"):
            return run["id"]
    sys.exit("the run didn't finish")


def record(browser, name: str, scene) -> None:
    videos = Path(tempfile.mkdtemp())
    ctx = browser.new_context(viewport=SIZE, record_video_dir=str(videos), record_video_size=SIZE)
    ctx.add_init_script(CURSOR_JS)
    page = ctx.new_page()
    t0 = time.monotonic()
    marks: dict[str, float] = {}
    scene(page, lambda label: marks.__setitem__(label, round(time.monotonic() - t0, 2)))
    video = page.video
    ctx.close()
    shutil.move(video.path(), RAW / f"{name}.webm")
    shutil.rmtree(videos, ignore_errors=True)
    (RAW / f"{name}-marks.json").write_text(json.dumps(marks, indent=2))
    print(f"-> demo/out/raw/{name}.webm", marks)


def scene_agent(page, mark) -> None:
    sign_in(page)
    page.goto(f"{WEB}/workflows")
    mark("open_form")
    beat(page, 1.2)
    glide_click(page, page.get_by_role("link", name="New from instructions"))
    page.wait_for_url("**/workflows/new")
    beat(page, 1)
    type_into(page, page.get_by_label("Start at this link"), f"{PORTAL}/login")
    field = page.get_by_label("What should it do?")
    glide_click(page, field)
    for line in INSTRUCTIONS.splitlines():
        field.press_sequentially(line, delay=28)
        field.press("Enter")
    beat(page, 1)
    snap(page, "agent-form")
    mark("submit")
    glide_click(page, page.get_by_role("button", name="Build it live"))
    page.wait_for_url("**/authoring/aut_*", wait_until="commit")
    mark("building")
    page.get_by_text("Waiting for you").or_(page.get_by_text("Workflow saved")).or_(
        page.get_by_text("Stopped")
    ).first.wait_for(timeout=900_000)
    if page.get_by_text("Approval needed").count():
        beat(page, 1.5)
        mark("approval")
        beat(page, 3)
        snap(page, "agent-approval")
        glide_click(page, page.get_by_role("button", name="Do it now"))
        mark("approved")
    page.get_by_text("Workflow saved").or_(page.get_by_text("Stopped")).first.wait_for(
        timeout=900_000
    )
    beat(page, 2)
    mark("saved")
    beat(page, 3)
    snap(page, "agent-saved")
    if page.get_by_text("Stopped").count():
        sys.exit("the agent stopped: see the page for why")
    glide_click(page, page.get_by_role("link", name="Review the steps"))
    page.wait_for_url("**/workflows/*?tab=steps")
    page.locator("main").get_by_text("Inputs").first.wait_for()
    mark("steps")
    beat(page, 2.5)
    snap(page, "agent-steps")
    page.mouse.wheel(0, 500)
    beat(page, 2.5)
    mark("end")


def scene_fix(run_id: str):
    def scene(page, mark) -> None:
        sign_in(page)
        page.goto(f"{WEB}/runs/{run_id}")
        page.get_by_text("Fix this workflow").wait_for()
        mark("start")
        beat(page, 2)
        box = page.get_by_placeholder("e.g. The bill takes")
        box.scroll_into_view_if_needed()
        type_into(page, box, HINT)
        beat(page, 1.5)
        page.get_by_role("button", name="Fix it with the agent").hover()
        beat(page, 2)
        snap(page, "agent-fix")
        mark("end")

    return scene


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    set_variant("original")
    token = api("/auth/login", {"email": EMAIL, "password": PASSWORD})["access"]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        record(browser, "20-agent", scene_agent)
        run_id = failed_run(token, workflows()["acme_invoice_northwind"]["id"])
        record(browser, "21-fix", scene_fix(run_id))
        browser.close()


if __name__ == "__main__":
    main()
