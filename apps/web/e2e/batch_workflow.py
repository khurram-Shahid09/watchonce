"""End-to-end batch: upload a CSV for a compiled Acme workflow, approve the first row's
checkpoint for the whole batch, download the results CSV; also download the Playwright
export. Prereqs as in run_workflow.py. Run from services/core:

    WATCHONCE_EMAIL=... WATCHONCE_PASSWORD=... WATCHONCE_WORKFLOW=wf_... \
      uv run --with playwright python -I ../../apps/web/e2e/batch_workflow.py
"""

import csv
import io
import os
import re
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

WEB = os.environ.get("WATCHONCE_WEB", "http://localhost:3000")
EMAIL = os.environ["WATCHONCE_EMAIL"]
PASSWORD = os.environ["WATCHONCE_PASSWORD"]
WORKFLOW = os.environ["WATCHONCE_WORKFLOW"]
SHOTS = Path(os.environ["SHOTS_DIR"]) if os.environ.get("SHOTS_DIR") else None
ROWS = [
    ("Northwind Ltd", "120.00", "2026-12-01", "Batch row 1"),
    ("City Power & Light", "75.50", "2026-12-15", "Batch row 2"),
    ("Adventure Works", "990", "2027-01-05", "Batch row 3"),
]

failures: list[str] = []


def check(ok: bool, message: str) -> None:
    print(("  ok   " if ok else "  FAIL ") + message)
    if not ok:
        failures.append(message)


with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
    csv_path = Path(tmp) / "invoices.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Vendor Name", "Amount", "Due Date", "Description"])
        writer.writerows(ROWS)

    browser = p.chromium.launch()
    context = browser.new_context(viewport={"width": 1280, "height": 900}, accept_downloads=True)
    page = context.new_page()
    page.goto(f"{WEB}/login")
    page.get_by_label("Email").fill(EMAIL)
    page.get_by_label("Password").fill(PASSWORD)
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url("**/workflows", wait_until="commit")

    page.goto(f"{WEB}/workflows/{WORKFLOW}?tab=batch")
    page.get_by_label("CSV file").set_input_files(str(csv_path))
    page.get_by_role("button", name="Start batch").click()
    page.wait_for_url("**/batches/bat_*", wait_until="commit")
    check(True, "batch started from a 3-row CSV")

    approve_all = page.get_by_role("button", name="Approve for all rows")
    approve_all.wait_for(timeout=180_000)
    check(page.get_by_text(re.compile("Row 1 is waiting for approval")).count() == 1, "row 1 paused at the checkpoint")
    if SHOTS:
        page.screenshot(path=str(SHOTS / "batch-waiting.png"), full_page=True)
    page.once("dialog", lambda d: d.accept())
    approve_all.click()

    expect(page.get_by_text(re.compile(r"3 of 3 done"))).to_be_visible(timeout=300_000)
    summary = page.get_by_text(re.compile(r"3 of 3 done")).inner_text()
    check("3 succeeded" in summary, f"all rows ran: {summary.strip()}")
    if SHOTS:
        page.screenshot(path=str(SHOTS / "batch-done.png"), full_page=True)

    with page.expect_download() as info:
        page.get_by_role("link", name="Download results CSV").click()
    results = list(csv.DictReader(io.StringIO(Path(info.value.path()).read_text(encoding="utf-8-sig"))))
    numbers = [r.get("invoice_number", "") for r in results]
    check(len(results) == 3 and all(re.fullmatch(r"INV-\d+", n) for n in numbers), f"results CSV has invoice numbers: {numbers}")
    check([r["status"] for r in results] == ["succeeded"] * 3, "every row succeeded in the results file")

    page.goto(f"{WEB}/workflows/{WORKFLOW}?tab=versions")
    with page.expect_download() as info:
        page.get_by_role("link", name="Download script").first.click()
    script = Path(info.value.path()).read_text(encoding="utf-8")
    compile(script, "workflow.py", "exec")
    check("def run(page" in script and "--vendor-name" in script, f"Playwright script downloaded ({len(script)} chars, compiles)")
    browser.close()

print(f"\n{'PASSED' if not failures else f'{len(failures)} FAILED'}")
sys.exit(1 if failures else 0)
