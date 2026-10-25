"""End-to-end: load the extension (E2E build) into Chromium, record the "create invoice" task
on the Acme portal, export the recording and check it. With WATCHONCE_PAT set, also connect
the extension to the API (WATCHONCE_API, default http://localhost:8000), upload, and check the
normalized steps once the compile worker has processed the recording.

Prereqs: the portal on http://localhost:3001 (pnpm dev:portal) and `pnpm --filter
@watchonce/extension build:e2e`. Run from services/core (it has Playwright available):

    uv run --with playwright python -I ../../apps/extension/e2e/record_acme.py [out.json]

The upload stage also needs the API, object storage and a compile worker:
    uv run celery -A config worker -Q compile --pool=solo
"""

import json
import os
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

PORTAL = "http://localhost:3001"
DIST = Path(__file__).resolve().parents[1] / "dist"
PASSWORD = "acme-demo"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else None
API = os.environ.get("WATCHONCE_API", "http://localhost:8000")
PAT = os.environ.get("WATCHONCE_PAT", "")

failures: list[str] = []


def check(ok: bool, message: str) -> None:
    print(("  ok   " if ok else "  FAIL ") + message)
    if not ok:
        failures.append(message)


manifest = json.loads((DIST / "manifest.json").read_text())
assert "E2E" in manifest["name"], "build with: pnpm --filter @watchonce/extension build:e2e"

with tempfile.TemporaryDirectory() as profile, sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        profile,
        channel="chromium",  # new headless mode, which supports extensions
        headless=True,
        viewport={"width": 1280, "height": 800},
        args=[f"--disable-extensions-except={DIST}", f"--load-extension={DIST}"],
    )
    worker = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker")
    ext_id = worker.url.split("/")[2]

    page = ctx.new_page()
    page.goto(f"{PORTAL}/login?variant=original")
    # Like browser autofill: the login form is already filled before recording starts.
    page.get_by_label("Username").fill("sara")
    page.get_by_label("Password").fill(PASSWORD)
    page.bring_to_front()
    tab_id = worker.evaluate(
        "async () => (await chrome.tabs.query({url: 'http://localhost:3001/*'}))[0].id"
    )

    # The popup page is just an extension page: use it to talk to the worker like the UI does.
    popup = ctx.new_page()
    popup.goto(f"chrome-extension://{ext_id}/popup/popup.html")
    send = lambda msg: popup.evaluate("m => chrome.runtime.sendMessage(m)", msg)  # noqa: E731
    started = send({"kind": "recording.start", "tabId": tab_id})
    check(started.get("session", {}).get("status") == "recording", "recording started")
    popup.close()

    # --- The task, done by "Sara" at human pace ---
    page.bring_to_front()
    page.wait_for_function("() => !!document.querySelector('watchonce-recorder')")
    check(True, "recording pill injected into the page")

    def act(locator, text: str | None = None) -> None:
        page.wait_for_timeout(1000)  # a quick human; Chrome allows ~2 screenshots per second
        locator.click()
        if text is not None:
            locator.press_sequentially(text, delay=35)

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
    act(page.get_by_label("Description"), "Card 4111 1111 1111 1111 on file")
    act(page.get_by_role("button", name="Submit"))
    page.wait_for_url("**/invoices/INV-*")
    invoice_number = page.get_by_test_id("invoice-number").inner_text()
    page.wait_for_timeout(1500)  # let the last capture land

    # A second tab on the same site must not be recorded.
    other = ctx.new_page()
    other.goto(f"{PORTAL}/login")
    other.get_by_label("Username").fill("intruder")
    other.close()

    popup = ctx.new_page()
    popup.goto(f"chrome-extension://{ext_id}/popup/popup.html")
    send = lambda msg: popup.evaluate("m => chrome.runtime.sendMessage(m)", msg)  # noqa: E731
    send({"kind": "recording.stop"})
    send({"kind": "recording.describe", "description": "Create a vendor invoice"})
    data = send({"kind": "recording.export"})

    uploaded: dict = {}
    if PAT:
        connected = send({"kind": "connection.set", "apiUrl": API, "token": PAT})
        check(bool((connected.get("connection") or {}).get("orgName")), "extension connected to the workspace")
        check(PAT not in json.dumps(connected), "the popup never receives the token back")
        send({"kind": "recording.upload"})
        deadline = time.time() + 60
        while time.time() < deadline:
            uploaded = send({"kind": "state.get"})["session"].get("upload") or {}
            if uploaded.get("state") in ("done", "failed"):
                break
            time.sleep(0.5)
        check(uploaded.get("state") == "done", f"upload finished ({uploaded.get('error') or uploaded.get('recordingId')})")
    worker_log = worker.evaluate("async () => (await chrome.storage.session.get('diag')).diag || []")
    ctx.close()

if worker_log:
    print("worker diagnostics:")
    for line in worker_log[:40]:
        print("  " + line)
events = data["events"]
raw = json.dumps(data)
if OUT:
    OUT.write_text(json.dumps(data, indent=2))
    print(f"wrote {OUT} ({len(raw) // 1024} KB)")

print(f"\n{len(events)} events, {len(data['frames'])} frames, invoice {invoice_number}")
for e in events:
    el = e["element"] or {}
    print(f"  {e['seq']:>2} {e['type']:<9} {el.get('role') or '':<9} {(el.get('accessible_name') or '')[:22]:<22} "
          f"value={e['value']!r:<22} frame={e['frame_ref']}")
print()

types = [e["type"] for e in events]
by = lambda t: [e for e in events if e["type"] == t]  # noqa: E731
named = lambda t, name: [e for e in by(t) if (e["element"] or {}).get("accessible_name") == name]  # noqa: E731

check(PASSWORD not in raw, "the password never appears anywhere in the recording")
user = [e for e in by("input") if (e["element"] or {}).get("label_text") == "Username"]
check(len(user) == 1 and user[0]["value"] == "sara" and user[0].get("prefilled"), "autofilled username recorded (prefilled) before Sign in")
check("4111" not in raw, "a card number typed into a normal field is masked")
pw = [e for e in by("input") if (e["element"] or {}).get("attrs", {}).get("type") == "password"]
check(len(pw) == 1 and pw[0]["value"] == "__SECRET__" and pw[0]["value_masked"], "password input recorded as __SECRET__ once")
check(types[0] == "navigate" and events[0]["nav"]["transition"] == "initial", "starts with the initial navigation")
check([e["value"] for e in by("input") if (e["element"] or {}).get("label_text") == "Amount"] == ["1250.50"],
      "keystrokes coalesced into one input with the final value")
check(len(named("click", "Sign in")) == 1, "Sign in click recorded once")
new_btn = by("click")
new_btn = [e for e in new_btn if (e["element"] or {}).get("attrs", {}).get("data-testid") == "new-invoice-btn"]
check(len(new_btn) == 1 and new_btn[0]["element"]["is_unique"]["testid"], "New invoice click has a unique test id")
check(len(named("click", "Northwind Ltd")) == 1, "custom dropdown option click recorded")
check(any(e["element"] and e["element"]["role"] == "combobox" and e["element"]["accessible_name"] == "Vendor"
          for e in by("click")), "custom dropdown opener recorded as combobox 'Vendor'")
check(any(e["url"].endswith("/dashboard") for e in by("navigate")), "navigations recorded")
check(len(data["frames"]) >= 3, "screenshots captured")
clicks = by("click")
check(all(e["frame_ref"] for e in clicks), "every click carries its before-action frame")
check(all(e["frame_ref"] in data["frames"] for e in events if e["frame_ref"]), "every frame_ref points to an exported frame")
check(len({e["frame_ref"] for e in clicks if "/invoices/new" in e["url"]}) >= 5, "form actions mostly have their own frames")
check(all(f.startswith("data:image/webp;base64,") for f in data["frames"].values()), "frames are WebP")
check("intruder" not in raw, "another tab on the same site was not recorded")
check(data["recording"]["description"] == "Create a vendor invoice", "task description saved")
check(len({e["seq"] for e in events}) == len(events) and types.count("navigate") >= 4, "seq unique; navigations present")



def api_get(path: str) -> dict:
    req = urllib.request.Request(f"{API}/api/v1{path}", headers={"Authorization": f"Bearer {PAT}"})
    with urllib.request.urlopen(req, timeout=10) as response:  # noqa: S310 - local test server
        return json.loads(response.read())


if PAT and uploaded.get("recordingId"):
    rec_id = uploaded["recordingId"]
    rec: dict = {}
    for _ in range(60):  # the compile worker normalizes it
        rec = api_get(f"/recordings/{rec_id}")
        if rec["candidate_count"] is not None or rec["status"] == "failed":
            break
        time.sleep(0.5)
    print(f"\nuploaded {rec_id}: status={rec['status']} frames={rec['frame_count']} candidates={rec['candidate_count']}")
    check(rec["frame_count"] == len(data["frames"]), "every frame uploaded")
    check(rec["candidate_count"] is not None, "compile worker normalized the recording")
    if rec["candidate_count"] is not None:
        result = api_get(f"/recordings/{rec_id}/candidates")
        steps = [(c["action"], (c.get("element") or {}).get("name")) for c in result["candidates"]]
        for c in result["candidates"]:
            value = c.get("value") or c.get("option_label") or ""
            kinds = [loc["kind"] for loc in c.get("target", {}).get("locators", [])]
            print(f"  {c['id']:>4} {c['action']:<8} {str((c.get('element') or {}).get('name')):<24} {value!s:<34} {kinds}")
        check(steps[0][0] == "navigate", "candidates start with a navigate step")
        check(("select", "Vendor") in steps, "custom dropdown became one select step")
        check(sum(1 for a, _ in steps if a == "fill") == 5, "five fills: username, password, amount, date, description")
        check(PASSWORD not in json.dumps(result) and "4111" not in json.dumps(result), "no secrets in candidates")
        check(len(steps) < len(events) * 0.7, f"normalizing removed noise ({len(events)} events -> {len(steps)} steps)")

print(f"\n{'PASSED' if not failures else f'{len(failures)} FAILED'}")
sys.exit(1 if failures else 0)
