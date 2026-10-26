"""Record the demo scenes as separate videos + screenshots (the "director" for the demo).

Each scene drives the real dashboard and the Acme portal with a visible cursor and
human-paced typing, so the clips can be cut straight into the demo video. Raw clips land
in demo/out/raw/NN-scene.webm, stills in demo/out/shots/. See docs/demo/03-demo-video-script.md.

Prereqs: everything running (docs/demo/01-local-test-guide.md) and the demo workspace
seeded (demo/scripts/seed_demo.py), or your own recording compiled in that workspace.

    cd services/core
    uv run --with playwright python -I ../../demo/scripts/capture_scenes.py            # all scenes
    uv run --with playwright python -I ../../demo/scripts/capture_scenes.py batch heal # some
"""

import html
import json
import os
import re
import shutil
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
WEB = os.environ.get("WATCHONCE_WEB", "http://localhost:3000")
PORTAL = os.environ.get("ACME_PORTAL", "http://localhost:3001")
EMAIL = os.environ.get("DEMO_EMAIL", "ap.lead@acme-demo.test")
PASSWORD = os.environ.get("DEMO_PASSWORD", "WatchOnce-demo-2026")
OUT = ROOT / "demo" / "out"
RAW, SHOTS = OUT / "raw", OUT / "shots"
SIZE = {"width": 1440, "height": 900}
INVOICES_CSV = ROOT / "demo" / "data" / "ap-invoices-october.csv"
FIRST_ROW = {"vendor": "Northwind Ltd", "amount": "1250.50", "due_date": "2026-11-15",
             "description": "PO-4471 Office chairs (12 units)"}  # fmt: skip

# A visible cursor that glides, and a ripple on every click (videos have no cursor).
CURSOR_JS = """
(() => {
  if (window.__woCursor) return; window.__woCursor = true;
  const add = () => {
    const hide = document.createElement('style');  // the Next.js dev badge isn't part of the product
    hide.textContent = 'nextjs-portal{display:none!important}';
    document.documentElement.appendChild(hide);
    const c = document.createElement('div');
    c.id = '__wo_cursor';
    c.style.cssText = 'position:fixed;left:0;top:0;width:22px;height:22px;margin:-3px 0 0 -3px;z-index:2147483647;pointer-events:none;transition:transform .35s cubic-bezier(.2,.7,.2,1);background:no-repeat url("data:image/svg+xml;utf8,<svg xmlns=%27http://www.w3.org/2000/svg%27 width=%2722%27 height=%2722%27><path d=%27M3 2l14 8-6 1.6L8 18z%27 fill=%27black%27 stroke=%27white%27 stroke-width=%271.5%27/></svg>")';
    document.documentElement.appendChild(c);
    addEventListener('mousemove', e => { c.style.transform = `translate(${e.clientX}px, ${e.clientY}px)`; }, true);
    addEventListener('mousedown', e => {
      const r = document.createElement('div');
      r.style.cssText = `position:fixed;left:${e.clientX - 18}px;top:${e.clientY - 18}px;width:36px;height:36px;border-radius:50%;background:rgba(37,99,235,.35);z-index:2147483646;pointer-events:none;transition:transform .45s ease-out,opacity .45s ease-out`;
      document.documentElement.appendChild(r);
      requestAnimationFrame(() => { r.style.transform = 'scale(1.8)'; r.style.opacity = '0'; });
      setTimeout(() => r.remove(), 500);
    }, true);
  };
  document.readyState === 'loading' ? addEventListener('DOMContentLoaded', add) : add();
})();
"""


def beat(page: Page, seconds: float = 1.5) -> None:
    """Room for the voice-over."""
    page.wait_for_timeout(int(seconds * 1000))


def glide_click(page: Page, locator) -> None:
    locator.scroll_into_view_if_needed()
    box = locator.bounding_box()
    if box:
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=12)
        page.wait_for_timeout(350)
    locator.click()


def type_into(page: Page, locator, text: str) -> None:
    glide_click(page, locator)
    locator.fill("")
    locator.press_sequentially(text, delay=45)


def snap(page: Page, name: str) -> None:
    page.screenshot(path=str(SHOTS / f"{name}.png"))


def set_variant(variant: str) -> None:
    req = urllib.request.Request(
        f"{PORTAL}/api/variant", data=json.dumps({"variant": variant}).encode(), method="PUT",
        headers={"Content-Type": "application/json", "x-admin-token": os.environ.get("ACME_ADMIN_TOKEN", "")},
    )  # fmt: skip
    urllib.request.urlopen(req, timeout=10).read()  # noqa: S310 - local portal


def sign_in(page: Page) -> None:
    page.goto(f"{WEB}/login")
    page.get_by_label("Email").fill(EMAIL)
    page.get_by_label("Password").fill(PASSWORD)
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url("**/workflows", wait_until="commit")


def portal_sign_in(page: Page, slow: bool = True) -> None:
    page.goto(f"{PORTAL}/login")
    user = page.get_by_label(re.compile("^(Username|User ID)$"))
    if slow:
        type_into(page, user, "sara")
        type_into(page, page.get_by_label("Password"), "acme-demo")
        glide_click(page, page.get_by_role("button", name=re.compile("^(Sign in|Log in)$")))
    else:
        user.fill("sara")
        page.get_by_label("Password").fill("acme-demo")
        page.get_by_role("button", name=re.compile("^(Sign in|Log in)$")).click()
    page.wait_for_url("**/dashboard")


def workflows() -> dict:
    path = OUT / "demo-workflows.json"
    if not path.exists():
        sys.exit("Run demo/scripts/seed_demo.py first (or set it up by hand; see the guide).")
    return json.loads(path.read_text())


def run_and_approve(page: Page, workflow_id: str, inputs: dict[str, str] | None) -> None:
    page.goto(f"{WEB}/workflows/{workflow_id}?tab=run")
    page.get_by_role("button", name="Run now").wait_for()
    beat(page, 1)
    for name, value in (inputs or {}).items():
        label = page.locator("label").filter(
            has=page.locator("span.font-medium", has_text=re.compile(rf"^{name.replace('_', ' ')}"))
        )
        field = label.locator("input").first
        if not label.count():
            continue  # this workflow names the input differently; keep the recorded example
        if field.get_attribute("type") == "date":
            glide_click(page, field)
            field.fill(value)  # a date picker can't be typed into
        else:
            type_into(page, field, value)
    beat(page, 0.8)
    glide_click(page, page.get_by_role("button", name="Run now"))
    page.wait_for_url("**/runs/run_*", wait_until="commit")
    page.get_by_text(re.compile("^Approval needed")).wait_for(timeout=180_000)
    beat(page, 3)  # the bot stopped before "Submit": let the viewer read it
    snap(page, f"approval-{workflow_id[-6:]}")
    glide_click(page, page.get_by_role("button", name="Approve and continue"))
    page.get_by_text(re.compile("^(Succeeded|Failed)$")).first.wait_for(timeout=180_000)
    beat(page, 1)
    page.reload()
    page.locator("main ol li").first.wait_for()


# --- scenes ---------------------------------------------------------------------------


def scene_portal(page: Page, wf: dict) -> None:
    """The legacy portal AP clerks fight with every month (no API)."""
    portal_sign_in(page)
    beat(page, 1.5)
    glide_click(page, page.get_by_role("link", name="Invoices", exact=True))
    page.wait_for_url("**/invoices")
    beat(page, 2)
    glide_click(page, page.get_by_test_id("new-invoice-btn"))
    page.wait_for_url("**/invoices/new")
    beat(page, 3)
    snap(page, "portal-new-invoice")


def scene_workflow(page: Page, wf: dict) -> None:
    """What the AI made from one recording: steps with screenshots, inputs, an SOP."""
    invoice = wf["acme_invoice_northwind"]["id"]
    sign_in(page)
    beat(page, 1.5)
    page.goto(f"{WEB}/workflows/{invoice}?tab=steps")
    page.locator("main ol li").first.wait_for()
    beat(page, 2)
    snap(page, "workflow-steps")
    for _ in range(6):
        page.mouse.wheel(0, 350)
        page.wait_for_timeout(700)
    beat(page, 1)
    glide_click(page, page.get_by_role("link", name="SOP", exact=True))
    page.wait_for_url("**tab=sop**")
    beat(page, 3)
    snap(page, "workflow-sop")
    for _ in range(4):
        page.mouse.wheel(0, 300)
        page.wait_for_timeout(700)
    beat(page, 1)


def scene_run(page: Page, wf: dict) -> None:
    """One invoice: watch the bot live; it stops for a human before Submit."""
    sign_in(page)
    run_and_approve(page, wf["acme_invoice_northwind"]["id"], FIRST_ROW)
    beat(page, 2)
    snap(page, "run-done")


def scene_batch(page: Page, wf: dict) -> None:
    """The whole October backlog from a CSV: one approval, then hands off."""
    invoice = wf["acme_invoice_northwind"]["id"]
    sign_in(page)
    page.goto(f"{WEB}/workflows/{invoice}?tab=batch")
    page.get_by_label("CSV file").wait_for()
    beat(page, 1.5)
    page.get_by_label("CSV file").set_input_files(str(INVOICES_CSV))
    beat(page, 2)
    glide_click(page, page.get_by_role("button", name="Start batch"))
    page.wait_for_url("**/batches/bat_*", wait_until="commit")
    approve_all = page.get_by_role("button", name="Approve for all rows")
    approve_all.wait_for(timeout=240_000)
    beat(page, 2.5)
    snap(page, "batch-waiting")
    page.once("dialog", lambda d: d.accept())
    glide_click(page, approve_all)
    rows = sum(1 for _ in INVOICES_CSV.open(encoding="utf-8")) - 1
    expect(page.get_by_text(re.compile(rf"{rows} of {rows} done"))).to_be_visible(timeout=1_200_000)
    beat(page, 2)
    snap(page, "batch-done")
    with page.expect_download() as info:
        glide_click(page, page.get_by_role("link", name="Download results CSV"))
    shutil.copy(info.value.path(), OUT / "batch-results.csv")
    beat(page, 1.5)


def scene_heal(page: Page, wf: dict) -> None:
    """IT ships 'Portal v2' overnight. The run heals itself; the owner approves the fix."""
    invoice = wf["acme_invoice_northwind"]["id"]
    sign_in(page)
    page.goto(f"{PORTAL}/admin/ui-variant")
    beat(page, 2)
    glide_click(page, page.get_by_role("button", name=re.compile("^Portal v2")))
    beat(page, 1)
    portal_sign_in(page, slow=False)  # show the changed portal: new labels, ids, layout
    glide_click(page, page.get_by_role("link", name="Invoices", exact=True))
    beat(page, 2.5)
    snap(page, "portal-v2")
    run_and_approve(page, invoice, {"vendor": "Contoso Supplies", "amount": "384.20",
                                     "due_date": "2026-11-10", "description": "PO-4480 Printer toner"})  # fmt: skip
    beat(page, 2)
    snap(page, "heal-run")
    page.goto(f"{WEB}/workflows/{invoice}?tab=heals")
    approve = page.get_by_role("button", name=re.compile("^Approve (fix|all)"))
    approve.first.wait_for()
    beat(page, 2)
    for _ in range(3):
        page.mouse.wheel(0, 350)
        page.wait_for_timeout(900)
    snap(page, "heal-review")
    page.mouse.wheel(0, -2000)
    beat(page, 1)
    glide_click(page, approve.first)
    expect(page.get_by_role("button", name=re.compile("^Approve (fix|all)"))).to_have_count(0, timeout=15_000)
    beat(page, 2)


def scene_injection(page: Page, wf: dict) -> None:
    """A page tells the 'AI' to delete all vendors. The bot does its job and nothing else."""
    invoice = wf["acme_invoice_northwind"]["id"]
    sign_in(page)
    set_variant("m8")
    portal_sign_in(page, slow=False)
    glide_click(page, page.get_by_role("link", name="Invoices", exact=True))
    page.get_by_text("Notice from IT").wait_for()
    beat(page, 3.5)
    snap(page, "injection-banner")
    run_and_approve(page, invoice, {"vendor": "Fabrikam Inc", "amount": "8900",
                                     "due_date": "2026-11-30", "description": "Q4 maintenance contract"})  # fmt: skip
    beat(page, 2.5)
    snap(page, "injection-run")


def scene_export(page: Page, wf: dict) -> None:
    """No lock-in: every workflow exports as a plain Playwright script."""
    invoice = wf["acme_invoice_northwind"]["id"]
    sign_in(page)
    page.goto(f"{WEB}/workflows/{invoice}?tab=versions")
    link = page.get_by_role("link", name="Download script").first
    link.wait_for()
    beat(page, 1.5)
    with page.expect_download() as info:
        glide_click(page, link)
    script = Path(info.value.path()).read_text(encoding="utf-8")
    (OUT / "exported_workflow.py").write_text(script, encoding="utf-8")
    page.set_content(
        "<body style='margin:0;background:#0b1020;color:#e5e7eb;font:15px/1.5 Consolas,monospace'>"
        f"<pre style='padding:28px'>{html.escape(script)}</pre></body>"
    )
    beat(page, 2)
    for _ in range(6):
        page.mouse.wheel(0, 400)
        page.wait_for_timeout(800)
    snap(page, "export-script")


def scene_analytics(page: Page, wf: dict) -> None:
    """What it was worth: hours saved, success rate, heals."""
    sign_in(page)
    page.goto(f"{WEB}/analytics?range=7d")
    page.get_by_text("Hours saved").wait_for()
    beat(page, 3)
    snap(page, "analytics")
    glide_click(page, page.get_by_role("link", name="30 days"))
    beat(page, 3)


SCENES = {
    "portal": scene_portal,
    "workflow": scene_workflow,
    "run": scene_run,
    "batch": scene_batch,
    "heal": scene_heal,
    "injection": scene_injection,
    "export": scene_export,
    "analytics": scene_analytics,
}


def reset_invoice_workflow(browser, wf: dict) -> None:
    """Make version 1 (recorded on the original portal) active again, so the heal scene
    heals for real even when the scenes are recorded more than once."""
    page = browser.new_page(viewport=SIZE)
    sign_in(page)
    page.goto(f"{WEB}/workflows/{wf['acme_invoice_northwind']['id']}?tab=versions")
    page.get_by_text("Version 1", exact=True).wait_for()
    row = page.locator("li").filter(has_text="Version 1").filter(has=page.get_by_role("button", name="Make active"))
    if row.count():
        page.once("dialog", lambda d: d.accept())
        row.get_by_role("button", name="Make active").click()
        page.wait_for_timeout(1500)
    page.close()


def main() -> None:
    wanted = sys.argv[1:] or list(SCENES)
    unknown = set(wanted) - set(SCENES)
    if unknown:
        sys.exit(f"Unknown scene(s): {', '.join(unknown)}. Scenes: {', '.join(SCENES)}")
    wf = workflows()
    RAW.mkdir(parents=True, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(slow_mo=60)
        set_variant("original")
        if "heal" in wanted:
            reset_invoice_workflow(browser, wf)
        for name in wanted:
            number = list(SCENES).index(name) + 1
            print(f"scene {number:02d} {name} ...", flush=True)
            context = browser.new_context(
                viewport=SIZE, record_video_dir=str(RAW / "tmp"), record_video_size=SIZE,
                accept_downloads=True,
            )  # fmt: skip
            context.add_init_script(CURSOR_JS)
            page = context.new_page()
            try:
                SCENES[name](page, wf)
            finally:
                video = page.video
                context.close()
                set_variant("original")
                if video:
                    target = RAW / f"{number:02d}-{name}.webm"
                    shutil.move(video.path(), target)
                    print(f"  -> {target.relative_to(ROOT)}")
        browser.close()
    shutil.rmtree(RAW / "tmp", ignore_errors=True)
    print(f"\nDone. Clips: {RAW}\nStills: {SHOTS}")


if __name__ == "__main__":
    main()
