"""Record every golden task with the real extension and save it under evals/golden/<id>/.

    pnpm --filter @watchonce/extension build:e2e
    cd services/core && uv run --with playwright python -I ../../evals/make_goldens.py [ids...]

Each task writes recording.json (the extension's export, screenshots included) and
expected.json (its answer key). Rebuild the normal extension afterwards.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from goldens import TASKS  # noqa: E402
from recorder import record  # noqa: E402

OUT = Path(__file__).resolve().parent / "golden"

wanted = set(sys.argv[1:])
for task in TASKS:
    if wanted and task["id"] not in wanted:
        continue
    print(f"recording {task['id']} ...", flush=True)
    data = record(task["start_url"], task["description"], task["task"])
    folder = OUT / task["id"]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "recording.json").write_text(json.dumps(data), encoding="utf-8")
    (folder / "expected.json").write_text(json.dumps(task["expected"], indent=2), encoding="utf-8")
    password = task["expected"].get("login", {}).get("password")
    leak = bool(password) and password in json.dumps({k: data[k] for k in ("recording", "events")})
    print(f"  {len(data['events'])} events, {len(data['frames'])} screenshots, password in file: {leak}")
