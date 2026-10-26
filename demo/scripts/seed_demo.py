"""Set up the "Acme Corp - Accounts Payable" demo workspace in one go.

Creates (or signs in to) the demo account, uploads three recordings of real AP tasks
(made with the extension, from evals/golden/) exactly like the extension does, waits for
the compile, saves the Acme portal login and sets each task's "minutes by hand".

Use it as a backup for the live recording in the demo, or to test everything else fast.
Needs the API, both workers, SeaweedFS and the Acme portal running (docs/demo/01-...).

    cd services/core
    uv run python -I ../../demo/scripts/seed_demo.py
"""

import base64
import json
import os
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
API = os.environ.get("WATCHONCE_API", "http://127.0.0.1:8000") + "/api/v1"
EMAIL = os.environ.get("DEMO_EMAIL", "ap.lead@acme-demo.test")
PASSWORD = os.environ.get("DEMO_PASSWORD", "WatchOnce-demo-2026")
ORG = os.environ.get("DEMO_ORG", "Acme Corp - Accounts Payable")
OUT = ROOT / "demo" / "out"

# golden id -> (task description as the AP clerk would type it, minutes it takes by hand)
TASKS = {
    "acme_invoice_northwind": ("Enter a vendor invoice in the Acme portal and submit it for approval", 4),
    "acme_add_vendor": ("Onboard a new vendor in the Acme portal", 3),
    "acme_approve_invoice": ("Approve the next invoice waiting in the Acme approvals queue", 1),
}
PORTAL_LOGIN = {"username": "sara", "password": "acme-demo"}


def session() -> httpx.Client:
    client = httpx.Client(base_url=API, timeout=60)
    login = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    if login.status_code != 200:
        reg = client.post(
            "/auth/register",
            json={"email": EMAIL, "password": PASSWORD, "name": "Sara (AP lead)", "org_name": ORG},
        )
        reg.raise_for_status()
        login = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
        print(f"created the demo account {EMAIL}")
    login.raise_for_status()
    client.headers["Authorization"] = f"Bearer {login.json()['access']}"
    return client


def upload(client: httpx.Client, golden: str, description: str) -> str:
    data = json.loads((ROOT / "evals" / "golden" / golden / "recording.json").read_text("utf-8"))
    meta = data["recording"]
    created = client.post(
        "/recordings",
        json={
            "description": description,
            "start_url": meta["startUrl"],
            "event_count": len(data["events"]),
            "duration_ms": meta["stoppedAt"] - meta["startedAt"],
            "frames": list(data["frames"]),
        },
    )
    created.raise_for_status()
    rec = created.json()
    events = {"format_version": data["format_version"], "recording": meta, "events": data["events"]}
    with httpx.Client(timeout=60) as s3:
        s3.put(
            rec["upload"]["events_url"],
            content=json.dumps(events).encode(),
            headers={"Content-Type": "application/json"},
        ).raise_for_status()
        for frame in rec["upload"]["frames"]:
            body = base64.b64decode(data["frames"][frame["name"]].split(",", 1)[1])
            s3.put(frame["url"], content=body, headers={"Content-Type": "image/webp"}).raise_for_status()
    client.post(f"/recordings/{rec['id']}/complete").raise_for_status()
    return rec["id"]


def wait_for_workflow(client: httpx.Client, recording_id: str) -> dict:
    for _ in range(240):  # an AI compile takes up to a minute or two
        rec = client.get(f"/recordings/{recording_id}").json()
        if rec["status"] == "failed":
            sys.exit(f"compile failed: {rec.get('error')}")
        if rec["status"] == "compiled":
            for wf in client.get("/workflows").json()["results"]:
                if wf["recording_id"] == recording_id:
                    return wf
        time.sleep(1)
    sys.exit("timed out waiting for the compile (is the compile worker running?)")


def main() -> None:
    client = session()
    recordings = client.get("/recordings", params={"limit": 100}).json()["results"]
    compiled = {r["description"]: r["id"] for r in reversed(recordings) if r["status"] == "compiled"}
    result = {}
    for golden, (description, minutes) in TASKS.items():
        if description in compiled:  # set up before: reuse it, don't make a duplicate
            recording_id = compiled[description]
            print(f"{golden}: already recorded, reusing it")
        else:
            print(f"{golden}: uploading the recording and compiling ...", flush=True)
            recording_id = upload(client, golden, description)
        wf = wait_for_workflow(client, recording_id)
        client.patch(f"/workflows/{wf['id']}", json={"manual_duration_sec": minutes * 60}).raise_for_status()
        version = client.get(f"/workflows/{wf['id']}/versions/{wf['active_version']['version']}").json()
        for secret in version["spec"].get("secrets", []):
            listed = client.get("/secrets").json()
            have = {s["name"] for s in (listed["results"] if isinstance(listed, dict) else listed)}
            if secret["name"] not in have:
                values = {f: PORTAL_LOGIN.get(f, "") for f in secret["fields"]}
                client.post("/secrets", json={"name": secret["name"], "values": values}).raise_for_status()
                print(f"  saved the portal login as '{secret['name']}'")
        inputs = [i["name"] for i in version["spec"].get("inputs", [])]
        print(f"  -> {wf['name']} ({wf['id']}), {len(version['spec']['steps'])} steps, inputs: {inputs}")
        result[golden] = {"id": wf["id"], "name": wf["name"], "recording_id": recording_id, "inputs": inputs}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "demo-workflows.json").write_text(json.dumps(result, indent=2))
    print(f"\nDemo workspace ready. Sign in at http://localhost:3000 as {EMAIL} / {PASSWORD}")


if __name__ == "__main__":
    main()
