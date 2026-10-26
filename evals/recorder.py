"""Record a task with the real WatchOnce extension (E2E build) in Chromium and return the
exported recording, exactly as a person would produce it from the popup.

Used to (re)build the golden recordings. Needs `pnpm --filter @watchonce/extension build:e2e`.
"""

import json
import tempfile
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import Locator, Page, sync_playwright

DIST = Path(__file__).resolve().parents[1] / "apps" / "extension" / "dist"

Act = Callable[..., None]


def record(start_url: str, description: str, task: Callable[[Page, Act], None]) -> dict:
    manifest = json.loads((DIST / "manifest.json").read_text())
    if "E2E" not in manifest["name"]:
        raise SystemExit("Build the test extension first: pnpm --filter @watchonce/extension build:e2e")
    origin = "{0.scheme}://{0.netloc}".format(urlsplit(start_url))

    with tempfile.TemporaryDirectory() as profile, sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            profile,
            channel="chromium",
            headless=True,
            viewport={"width": 1280, "height": 800},
            args=[f"--disable-extensions-except={DIST}", f"--load-extension={DIST}"],
        )
        worker = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker")
        ext_id = worker.url.split("/")[2]
        page = ctx.new_page()
        page.goto(start_url)
        page.bring_to_front()
        tab_id = worker.evaluate(
            "async (origin) => (await chrome.tabs.query({url: origin + '/*'}))[0].id", origin
        )
        popup = ctx.new_page()
        popup.goto(f"chrome-extension://{ext_id}/popup/popup.html")

        def send(msg: dict) -> dict:
            return popup.evaluate("m => chrome.runtime.sendMessage(m)", msg)

        assert send({"kind": "recording.start", "tabId": tab_id})["session"]["status"] == "recording"
        popup.close()
        page.bring_to_front()
        page.wait_for_function("() => !!document.querySelector('watchonce-recorder')")

        def act(locator: Locator, text: str | None = None, *, press: str | None = None) -> None:
            page.wait_for_timeout(1000)  # human pace; Chrome allows ~2 screenshots per second
            locator.click()
            if text is not None:
                locator.press_sequentially(text, delay=30)
            if press:
                page.wait_for_timeout(400)
                locator.press(press)

        task(page, act)
        page.wait_for_timeout(1500)  # let the last screenshot land

        popup = ctx.new_page()
        popup.goto(f"chrome-extension://{ext_id}/popup/popup.html")
        send({"kind": "recording.stop"})
        send({"kind": "recording.describe", "description": description})
        data = send({"kind": "recording.export"})
        ctx.close()
    return data
