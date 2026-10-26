"""Day 14 E2E: analytics (hours saved), the manual-time editor, security headers, rate limits.

Registers a throwaway workspace, seeds one workflow with runs through Django, then drives
the dashboard. Needs the API (:8000) and dashboard (:3000) running.

    cd services/core && uv run --with playwright python -I ../../apps/web/e2e/analytics_workflow.py
"""

import os
import subprocess
import sys
import uuid
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

WEB = os.environ.get("WEB_URL", "http://localhost:3000")
API = os.environ.get("API_URL", "http://localhost:8000")
CORE = Path(__file__).resolve().parents[3] / "services" / "core"
EMAIL = f"e2e-{uuid.uuid4().hex[:8]}@analytics.test"
PASSWORD = f"pw-{uuid.uuid4().hex}"

SEED = """
from accounts.models import User
from runs.models import Run
from workflows.models import Workflow
from workflows.service import create_version
user = User.objects.get(email=EMAIL)
org = user.memberships.first().org
spec = {"spec_version": "1.0", "name": "Enter invoice", "allowed_domains": ["acme.test"],
        "start_url": "https://acme.test/", "inputs": [], "secrets": [], "outputs": [],
        "steps": [{"id": "s1", "action": "navigate", "intent": "Open", "url": "https://acme.test/"}],
        "settings": {}}
wf = Workflow.objects.create(org=org, name="Enter invoice")
create_version(wf, spec, created_by="e2e", activate=True)
wf.refresh_from_db()
for status in ["succeeded"] * 6 + ["failed"]:
    Run.objects.create(org=org, workflow=wf, version=wf.active_version, triggered_by="e2e", status=status)
print(wf.id)
"""

failures: list[str] = []


def check(ok: bool, message: str) -> None:
    print(("  ok   " if ok else "  FAIL ") + message)
    if not ok:
        failures.append(message)


reg = httpx.post(
    f"{API}/api/v1/auth/register",
    json={"email": EMAIL, "password": PASSWORD, "name": "E2E", "org_name": "Analytics E2E"},
)
reg.raise_for_status()
seeded = subprocess.run(
    ["uv", "run", "python", "manage.py", "shell", "-c", f"EMAIL={EMAIL!r}\n{SEED}"],
    cwd=CORE,
    capture_output=True,
    text=True,
    check=True,
)
workflow_id = seeded.stdout.strip().splitlines()[-1]

with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()

    response = page.goto(f"{WEB}/login")
    headers = response.headers if response else {}
    check(headers.get("x-frame-options") == "DENY", "dashboard refuses to be framed")
    check("frame-ancestors 'none'" in headers.get("content-security-policy", ""), "CSP frame-ancestors set")
    check(headers.get("x-content-type-options") == "nosniff", "nosniff header set")
    check("x-powered-by" not in headers, "no X-Powered-By header")

    page.get_by_label("Email").fill(EMAIL)
    page.get_by_label("Password").fill(PASSWORD)
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url("**/workflows", wait_until="commit")

    page.goto(f"{WEB}/analytics")
    expect(page.get_by_role("heading", name="Analytics")).to_be_visible()
    expect(page.get_by_text("Hours saved")).to_be_visible()
    check(page.get_by_text("1 workflow(s) without a manual time").is_visible(), "flags the workflow with no manual time")
    check(page.get_by_text("86%").is_visible(), "success rate 6 of 7 = 86%")
    check(page.get_by_role("link", name="Set").is_visible(), "the table links to set the manual time")

    page.goto(f"{WEB}/workflows/{workflow_id}")
    page.get_by_role("button", name="Set it").click()
    page.get_by_label("Minutes by hand").fill("15")
    page.get_by_role("button", name="Save").click()
    expect(page.get_by_text("Takes about 15 min by hand")).to_be_visible()
    check(True, "manual time saved from the workflow page")

    page.goto(f"{WEB}/analytics?range=30d")
    expect(page.get_by_text("1.5 h").first).to_be_visible()  # 6 successful runs x 15 minutes
    check(True, "hours saved = 6 runs x 15 min = 1.5 h (30-day range)")
    check(page.get_by_role("link", name="30 days").get_attribute("aria-current") == "page", "range switch")
    if os.environ.get("SHOTS_DIR"):
        page.screenshot(path=str(Path(os.environ["SHOTS_DIR"]) / "analytics.png"), full_page=True)
    browser.close()

# API limit: the default is 60/min per token; the 61st call in a minute gets 429.
token = httpx.post(f"{API}/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}).json()["access"]
with httpx.Client(headers={"Authorization": f"Bearer {token}"}) as client:  # one connection:
    codes = [client.get(f"{API}/api/v1/workflows").status_code for _ in range(65)]  # all in a minute
check(codes.count(429) >= 1 and codes[0] == 200, f"API rate limit kicks in ({codes.count(200)} ok, then 429)")
api_headers = httpx.get(f"{API}/healthz").headers
check(api_headers.get("x-frame-options") == "DENY", "API refuses to be framed")

print("PASSED" if not failures else f"FAILED: {len(failures)}")
sys.exit(1 if failures else 0)
