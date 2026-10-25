"""The exported script is valid Python and really runs the workflow (in its own process)."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from engine.export.playwright import export_playwright
from engine.runner.tests.site import Site
from engine.runner.tests.test_executor import spec_for


def test_script_compiles_and_is_free_of_injection(tmp_path: Path) -> None:
    spec = spec_for("127.0.0.1:9")
    spec["steps"][1]["intent"] = 'Type """; import os; os.system("calc") #'
    script = export_playwright(spec, version=3)
    compile(script, "workflow.py", "exec")
    assert 'os.system("calc")' not in script.split('"""')[2]  # only ever inside repr'd strings
    assert "APP_LOGIN_PASSWORD" in script
    assert "--vendor-name" in script


@pytest.mark.browser
def test_exported_script_runs_the_workflow(tmp_path: Path) -> None:
    pytest.importorskip("playwright.sync_api")
    with Site() as site:
        script = tmp_path / "invoice.py"
        script.write_text(export_playwright(spec_for(site.host), version=1), encoding="utf-8")
        env = {**os.environ, "APP_LOGIN_USERNAME": "sara", "APP_LOGIN_PASSWORD": "hunter2"}
        result = subprocess.run(  # noqa: S603 - our own generated script
            [sys.executable, str(script), "--yes", "--vendor-name", "Northwind Ltd",
             "--amount", "99.5", "--due-date", "2026-12-24"],
            capture_output=True, text=True, env=env, timeout=120, check=False,
        )  # fmt: skip
    lines = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
    assert lines, result.stdout + result.stderr
    assert lines[-1] == {
        "row": 1,
        "status": "succeeded",
        "outputs": {"invoice_number": "INV-48213"},
    }
