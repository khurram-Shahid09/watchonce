"""Export a workflow version as a standalone Playwright (Python) script
(docs/08 "Playwright export").

The script is plain, readable code: one block per step with the recorded locators as
fallbacks, inputs as command-line options or a CSV, logins from environment variables,
and checkpoints as a yes/no prompt. There is no self-healing in it; that stays in
WatchOnce. Every string from the spec is embedded with ``repr``, so nothing in a workflow
can inject code into the script.
"""

import re
from typing import Any

HELPERS = r'''
import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import date

from playwright.sync_api import Locator, Page, sync_playwright

TIMEOUT_MS = {timeout}


def locate(page: Page, candidates, intent: str) -> Locator:
    """The first locator that matches exactly one visible element (tried until timeout)."""
    deadline = time.monotonic() + TIMEOUT_MS / 1000
    while True:
        for make in candidates:
            loc = make(page).filter(visible=True)
            try:
                if loc.count() == 1:
                    return loc
            except Exception:
                pass
        if time.monotonic() > deadline:
            raise SystemExit(f"Couldn't find the element for: {{intent}}")
        page.wait_for_timeout(250)


_REF = re.compile(r"\{{\{{\s*([^}}|]+?)\s*((?:\|[^}}]*)?)\}}\}}")


def render(template: str, inputs: dict, secrets: dict, outputs: dict) -> str:
    def value(m):
        ref, filters = m.group(1).strip(), m.group(2)
        if ref.startswith("secrets."):
            _, name, field = ref.split(".")
            return secrets[name][field]
        v = outputs[ref.split(".", 1)[1]] if ref.startswith("outputs.") else inputs[ref]
        for f in filter(None, (x.strip() for x in filters.split("|"))):
            kind, arg = f.split(":", 1)
            if kind == "number":
                v = f"{{float(v):.{{int(arg)}}f}}"
            elif kind == "date":
                d = date.fromisoformat(str(v))
                parts = {{"YYYY": f"{{d.year:04d}}", "YY": f"{{d.year % 100:02d}}", "MM": f"{{d.month:02d}}",
                         "M": str(d.month), "DD": f"{{d.day:02d}}", "D": str(d.day)}}
                v = re.sub(r"YYYY|YY|MM|M|DD|D", lambda t: parts[t.group(0)], arg.strip('"'))
        return str(v)

    return _REF.sub(value, template)


def choose(page: Page, field: Locator, label: str) -> None:
    """Native <select> or a custom dropdown (open it, click the option)."""
    if field.evaluate("e => e.tagName") == "SELECT":
        field.select_option(label=label)
        return
    field.click()
    locate(page, [lambda p: p.get_by_role("option", name=label, exact=True),
                  lambda p: p.get_by_text(label, exact=True)], f"option {{label!r}}").click()


def expect_url(page: Page, pattern: str) -> None:
    import fnmatch
    from urllib.parse import urlsplit

    deadline = time.monotonic() + TIMEOUT_MS / 1000
    while not fnmatch.fnmatchcase(page.url if pattern.startswith("http") else urlsplit(page.url).path, pattern):
        if time.monotonic() > deadline:
            raise SystemExit(f"Expected the URL to match {{pattern}}, got {{page.url}}")
        page.wait_for_timeout(200)


def approve(step: str, intent: str, reason: str, auto: bool) -> None:
    if auto:
        print(f"[{{step}}] {{intent}}: approved by --yes")
        return
    answer = input(f"[{{step}}] {{intent}}. {{reason}} Continue? [y/N] ")
    if answer.strip().lower() not in ("y", "yes"):
        raise SystemExit(f"Stopped at {{step}}: not approved")
'''


def _py(value: Any) -> str:
    return repr(value)


def _locator_lambdas(locators: list[dict[str, Any]]) -> str:
    out = []
    for loc in locators:
        kind = loc["kind"]
        exact = bool(loc.get("exact", False))
        if kind == "testid":
            out.append(f"lambda p: p.get_by_test_id({_py(loc['value'])})")
        elif kind == "role":
            name = loc.get("name")
            if name:
                out.append(
                    f"lambda p: p.get_by_role({_py(loc['role'])}, name={_py(name)}, exact={exact})"
                )
            else:
                out.append(f"lambda p: p.get_by_role({_py(loc['role'])})")
        elif kind == "label":
            out.append(f"lambda p: p.get_by_label({_py(loc['value'])}, exact={exact})")
        elif kind == "placeholder":
            out.append(f"lambda p: p.get_by_placeholder({_py(loc['value'])}, exact={exact})")
        elif kind == "text":
            out.append(f"lambda p: p.get_by_text({_py(loc['value'])}, exact={exact})")
        elif kind == "css":
            out.append(f"lambda p: p.locator({_py(loc['value'])})")
        elif kind == "xpath":
            out.append(f"lambda p: p.locator({_py('xpath=' + loc['value'])})")
    return "[" + ", ".join(out) + "]"


def _arg(name: str) -> str:
    return "--" + name.replace("_", "-")


def _step_code(step: dict[str, Any]) -> list[str]:
    sid, action, intent = step["id"], step["action"], step["intent"]
    lines = [f"    # {sid}: {intent}".replace("\n", " ")]

    def r(template: str) -> str:
        return f"render({_py(template)}, inputs, secrets, outputs)"

    target = None
    if step.get("target"):
        target = f"locate(page, {_locator_lambdas(step['target']['locators'])}, {_py(intent)})"
    checkpoint = (step.get("checkpoint") or {}).get("type") == "approval"
    if checkpoint:
        reason = step["checkpoint"].get("reason", "")
        if target:
            lines.append(f"    el = {target}")
            lines.append("    el.evaluate(\"e => e.style.outline = '3px solid #f59e0b'\")")
            target = "el"
        lines.append(f"    approve({_py(sid)}, {_py(intent)}, {_py(reason)}, auto_approve)")
    if action == "navigate":
        lines.append(f"    page.goto({r(step['url'])}, wait_until='domcontentloaded')")
    elif action == "click":
        lines.append(f"    {target}.click()")
    elif action == "fill":
        lines.append(f"    {target}.fill({r(step['value'])})")
    elif action == "select":
        if "label" in step:
            lines.append(f"    choose(page, {target}, {r(step['label'])})")
        else:
            lines.append(f"    {target}.select_option(value={r(step['value'])})")
    elif action in ("check", "uncheck"):
        lines.append(f"    {target}.{action}()")
    elif action == "press":
        lines.append(
            f"    {target}.press({_py(step['key'])})"
            if target
            else f"    page.keyboard.press({_py(step['key'])})"
        )
    elif action in ("wait_for", "assert"):
        lines.extend(_condition_code(step["condition"], r))
    elif action == "extract":
        lines.append(f"    text = {target}.inner_text()")
        if step.get("pattern"):
            lines.append(f"    match = re.search({_py(step['pattern'])}, text)")
            lines.append(
                f"    if not match: raise SystemExit({_py(f'Nothing matched for {step["output"]}')})"
            )
            lines.append(f"    outputs[{_py(step['output'])}] = match.group(0)")
        else:
            lines.append(f"    outputs[{_py(step['output'])}] = text.strip()")
    if step.get("assert_after"):
        lines.extend(_condition_code(step["assert_after"], r))
    elif action in ("click", "press", "select"):
        lines.append("    page.wait_for_load_state('load')")
    return lines


def _condition_code(cond: dict[str, Any], r) -> list[str]:
    kind = cond["type"]
    if kind == "url_matches":
        return [f"    expect_url(page, {_py(cond['value'])})"]
    if kind == "text_visible":
        return [
            f"    page.get_by_text({r(cond['value'])}).first.wait_for(state='visible', timeout=TIMEOUT_MS)"
        ]
    if kind == "network_idle":
        return ["    page.wait_for_load_state('networkidle')"]
    if kind == "element_visible":
        return [f"    locate(page, {_locator_lambdas(cond['target']['locators'])}, 'element')"]
    return []


def export_playwright(spec: dict[str, Any], *, version: int) -> str:
    inputs = spec.get("inputs", [])
    secrets = spec.get("secrets", [])
    env_names = {
        (s["name"], f): re.sub(r"[^A-Z0-9]+", "_", f"{s['name']}_{f}".upper())
        for s in secrets
        for f in s["fields"]
    }
    timeout = int(spec.get("settings", {}).get("default_timeout_ms", 15000))

    doc = [
        f"{spec['name']} (WatchOnce workflow, version {version}).",
        "",
        "Setup:  pip install playwright && playwright install chromium",
        "Run:    python this_file.py " + " ".join(f"{_arg(i['name'])} VALUE" for i in inputs),
        "        python this_file.py --csv rows.csv    (one run per row; columns named like the inputs)",
        "Options: --yes approves checkpoints without asking; --headed shows the browser.",
    ]
    if env_names:
        doc.append(
            "Logins are read from environment variables: " + ", ".join(env_names.values()) + "."
        )
    doc.append(
        "There is no self-healing in this script: if the website changes, it stops with an error."
    )
    # The docstring holds workflow text: keep it from closing the string or escaping.
    text = "\n".join(doc).replace("\\", "/").replace('"""', "'''")
    header = '#!/usr/bin/env python3\n"""' + text + '\n"""'

    body = [
        "",
        "",
        "def run(page: Page, inputs: dict, secrets: dict, auto_approve: bool) -> dict:",
        "    outputs: dict = {}",
    ]
    for step in spec["steps"]:
        body.extend(_step_code(step))
    body.append("    return outputs")

    types = {"number": "float", "integer": "int", "boolean": "str", "date": "str", "string": "str"}
    main = [
        "",
        "",
        "def main() -> None:",
        f"    parser = argparse.ArgumentParser(description={_py(spec['name'])})",
    ]
    for i in inputs:
        help_text = i.get("description") or i["name"]
        if i.get("example") is not None:
            help_text += f" (e.g. {i['example']})"
        if i["type"] == "date":
            help_text += " as YYYY-MM-DD"
        main.append(
            f"    parser.add_argument({_py(_arg(i['name']))}, dest={_py(i['name'])}, type={types[i['type']]}, help={_py(help_text)})"
        )
    main += [
        "    parser.add_argument('--csv', help='Run once per row of this CSV file')",
        "    parser.add_argument('--yes', action='store_true', help='Approve checkpoints without asking')",
        "    parser.add_argument('--headed', action='store_true', help='Show the browser')",
        "    args = parser.parse_args()",
        "    secrets: dict = {}",
    ]
    for (name, field), env in env_names.items():
        main.append(
            f"    secrets.setdefault({_py(name)}, {{}})[{_py(field)}] = os.environ.get({_py(env)}) or sys.exit({_py(f'Set {env}')})"
        )
    names = [i["name"] for i in inputs]
    main += [
        f"    names = {_py(names)}",
        "    if args.csv:",
        "        with open(args.csv, newline='', encoding='utf-8-sig') as f:",
        "            rows = [{k.strip().lower().replace(' ', '_'): v for k, v in row.items()} for row in csv.DictReader(f)]",
        "    else:",
        "        rows = [{n: getattr(args, n) for n in names}]",
        "    with sync_playwright() as p:",
        "        browser = p.chromium.launch(headless=not args.headed)",
        "        for n, row in enumerate(rows, start=1):",
        "            context = browser.new_context()",
        "            page = context.new_page()",
        "            page.set_default_timeout(TIMEOUT_MS)",
        "            try:",
        "                outputs = run(page, row, secrets, args.yes)",
        "                print(json.dumps({'row': n, 'status': 'succeeded', 'outputs': outputs}))",
        "            except SystemExit as exc:",
        "                print(json.dumps({'row': n, 'status': 'failed', 'error': str(exc)}))",
        "            finally:",
        "                context.close()",
        "        browser.close()",
        "",
        "",
        'if __name__ == "__main__":',
        "    main()",
        "",
    ]
    return header + "\n" + HELPERS.format(timeout=timeout) + "\n".join(body) + "\n".join(main)
