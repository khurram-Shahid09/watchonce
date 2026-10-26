"""Scene 00 for the demo video: a person records the invoice task with the real extension.

Records two clips: the portal while the task is done (with the recorder's on-page pill)
and the extension screen where the task is described. Needs the test build of the
extension (`pnpm --filter @watchonce/extension build:e2e`); rebuild the normal one after.

    cd services/core
    uv run --with playwright python -I ../../demo/scripts/capture_recording.py
"""

import shutil
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from capture_scenes import CURSOR_JS, RAW, SIZE, glide_click, type_into  # noqa: E402

DIST = ROOT / "apps" / "extension" / "dist"
PORTAL = "http://localhost:3001"

with tempfile.TemporaryDirectory() as profile, sync_playwright() as p:
    if "E2E" not in (DIST / "manifest.json").read_text():
        sys.exit("Build the test extension first: pnpm --filter @watchonce/extension build:e2e")
    videos = Path(tempfile.mkdtemp())
    ctx = p.chromium.launch_persistent_context(
        profile, channel="chromium", headless=True, viewport=SIZE, slow_mo=60,
        record_video_dir=str(videos), record_video_size=SIZE,
        args=[f"--disable-extensions-except={DIST}", f"--load-extension={DIST}"],
    )  # fmt: skip
    ctx.add_init_script(CURSOR_JS)
    worker = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker")
    ext = worker.url.split("/")[2]
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(f"{PORTAL}/login?variant=original")
    tab = worker.evaluate("async () => (await chrome.tabs.query({url: 'http://localhost:3001/*'}))[0].id")
    popup = ctx.new_page()
    popup.goto(f"chrome-extension://{ext}/popup/popup.html")
    popup.evaluate("m => chrome.runtime.sendMessage(m)", {"kind": "recording.start", "tabId": tab})
    page.bring_to_front()
    page.wait_for_function("() => !!document.querySelector('watchonce-recorder')")
    page.wait_for_timeout(1500)

    def act(locator, text=None):
        page.wait_for_timeout(700)
        if text is None:
            glide_click(page, locator)
        else:
            type_into(page, locator, text)

    act(page.get_by_label("Username"), "sara")
    act(page.get_by_label("Password"), "acme-demo")
    act(page.get_by_role("button", name="Sign in"))
    page.wait_for_url("**/dashboard")
    act(page.get_by_role("link", name="Invoices", exact=True))
    page.wait_for_url("**/invoices")
    act(page.get_by_test_id("new-invoice-btn"))
    page.wait_for_url("**/invoices/new")
    act(page.get_by_label("Vendor"))
    act(page.get_by_role("option", name="Northwind Ltd"))
    act(page.get_by_label("Amount"), "1250.50")
    act(page.get_by_label("Due date"), "11/15/2026")
    act(page.get_by_label("Description"), "PO-4471 Office chairs (12 units)")
    act(page.get_by_role("button", name="Submit"))
    page.wait_for_url("**/invoices/INV-*")
    page.wait_for_timeout(2500)

    # The extension: stop, describe the task.
    popup.evaluate("m => chrome.runtime.sendMessage(m)", {"kind": "recording.stop"})
    popup.reload()
    popup.bring_to_front()
    popup.wait_for_timeout(1200)
    describe = popup.locator("#description")
    describe.wait_for()
    type_into(popup, describe, "Enter a vendor invoice and submit it for approval")
    popup.wait_for_timeout(800)
    popup.locator("#upload").hover()
    popup.wait_for_timeout(2500)

    portal_video, popup_video = page.video, popup.video
    ctx.close()
    RAW.mkdir(parents=True, exist_ok=True)
    shutil.move(portal_video.path(), RAW / "00-record-portal.webm")
    shutil.move(popup_video.path(), RAW / "00-record-popup.webm")
    shutil.rmtree(videos, ignore_errors=True)
    print("-> demo/out/raw/00-record-portal.webm, 00-record-popup.webm")
