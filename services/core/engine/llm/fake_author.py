"""The fake provider's authoring agent: follows plain one-line instructions mechanically.

Understands lines like these (numbering and bullets are fine):
    Go to https://example.com/login
    Log in with my saved login acme_login
    Type 1250.50 in Amount            (also: enter / fill)
    Select Northwind Ltd in Vendor    (also: choose)
    Check Urgent / Uncheck Urgent
    Click Submit                      (also: press / tap; "Press Enter" presses the key)
    Wait for Invoice created
    Read Invoice number as invoice_number

Each line becomes one or more actions; progress is the number of successful steps so far.
Good for tests, CI and an offline demo; the real models handle free-form instructions.
"""

import re
from typing import Any

from engine.spec.validate import RISKY_VERBS

from .types import AuthorAction, AuthorRequest

_RISKY = re.compile(rf"\b({'|'.join(RISKY_VERBS)})\w*\b", re.IGNORECASE)
_BULLET = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s*")
_URL = re.compile(r"https?://\S+")
_LOGIN_FIELDS = ("username", "user", "email", "login")


def _action(**fields: Any) -> AuthorAction:
    base: dict[str, Any] = {
        "status": "act", "action": "", "candidate_id": "", "intent": "", "value_kind": "none",
        "value": "", "input_name": "", "input_type": "", "secret_name": "", "secret_field": "",
        "key": "", "url": "", "wait_text": "", "output_name": "", "output_type": "", "pattern": "",
        "risky": False, "explanation": "", "workflow_name": "", "summary": "",
    }  # fmt: skip
    return AuthorAction(**{**base, **fields})


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 1 or w.isdigit()}


def _best(candidates: list[dict[str, Any]], query: str, kinds: tuple[str, ...] = ()) -> str:
    """Id of the candidate whose name, label or placeholder shares most words with ``query``."""
    wanted = _words(query)
    best, best_score = "", 0.0
    for c in candidates:
        if kinds and c.get("role") not in kinds and c.get("tag") not in kinds:
            continue
        names = (
            " ".join(str(c.get(k) or "") for k in ("name", "label", "text", "placeholder"))
            + " "
            + " ".join(str(v) for v in (c.get("attributes") or {}).values())
        )
        have = _words(names)
        if not have:
            continue
        score = len(wanted & have) / max(len(wanted), 1)
        if (c.get("name") or "").strip().lower() == query.strip().lower():
            score += 1  # an exact name wins over a partial one
        if score > best_score:
            best, best_score = c["id"], score
    return best if best_score > 0 else ""


def _plan(req: AuthorRequest) -> list[dict[str, Any]]:
    """The instructions as a list of atomic operations (independent of the page)."""
    ops: list[dict[str, Any]] = []
    for raw in req.instructions.splitlines():
        line = _BULLET.sub("", raw).strip().rstrip(".")
        if not line:
            continue
        low = line.lower()
        url = _URL.search(line)
        if re.match(r"^(go to|open|navigate to|visit)\b", low) and url:
            ops.append({"op": "navigate", "url": url.group(0).rstrip(".,")})
        elif m := re.match(
            r"^(?:log ?in|sign in)\b.*?\b(?:login|credentials)\s+([a-z][a-z0-9_]*)", low
        ):
            ops.append({"op": "login", "secret": m.group(1)})
        elif m := re.match(
            r"^(?:type|enter|fill(?: in)?)\s+[\"']?(.+?)[\"']?\s+(?:in|into)\s+(?:the\s+)?(.+?)(?:\s+(?:field|box))?$",
            line,
            re.I,
        ):
            ops.append({"op": "fill", "value": m.group(1), "field": m.group(2)})
        elif m := re.match(
            r"^(?:select|choose|pick)\s+[\"']?(.+?)[\"']?\s+(?:in|from|for)\s+(?:the\s+)?(.+?)$",
            line,
            re.I,
        ):
            ops.append({"op": "select", "value": m.group(1), "field": m.group(2)})
        elif m := re.match(r"^(check|uncheck|tick|untick)\s+(?:the\s+)?(.+)$", line, re.I):
            verb = "uncheck" if m.group(1).lower() in ("uncheck", "untick") else "check"
            ops.append({"op": verb, "field": m.group(2)})
        elif m := re.match(r"^press\s+(enter|tab|escape)$", low):
            ops.append({"op": "press", "key": m.group(1).capitalize()})
        elif m := re.match(
            r"^(?:click|press|tap)\s+(?:on\s+)?(?:the\s+)?[\"']?(.+?)[\"']?(?:\s+(?:button|link|tab))?$",
            line,
            re.I,
        ):
            ops.append({"op": "click", "name": m.group(1)})
        elif m := re.match(
            r"^wait (?:for|until)\s+[\"']?(.+?)[\"']?(?:\s+(?:appears|shows|is shown))?$",
            line,
            re.I,
        ):
            ops.append({"op": "wait", "text": m.group(1)})
        elif m := re.match(
            r"^(?:read|get|extract|copy)\s+(?:the\s+)?(.+?)\s+as\s+([a-z][a-z0-9_]*)$", line, re.I
        ):
            ops.append({"op": "extract", "label": m.group(1), "name": m.group(2).lower()})
    return ops


def _expand(op: dict[str, Any], req: AuthorRequest) -> list[dict[str, Any]]:
    if op["op"] != "login":
        return [op]
    secret = next((s for s in req.secrets if s["name"] == op["secret"]), None)
    fields = secret["fields"] if secret else ["username", "password"]
    user_field = next((f for f in _LOGIN_FIELDS if f in fields), fields[0])
    return [
        {"op": "fill_secret", "secret": op["secret"], "field": user_field, "find": user_field},
        {"op": "fill_secret", "secret": op["secret"], "field": "password", "find": "password"},
        {"op": "click", "name": "sign in log in login"},
    ]


def _value_after(page_text: str, label: str) -> str:
    """The value printed after ``label`` in the page text (same line, or the next one)."""
    m = re.search(re.escape(label) + r"\s*[:#]?\s*\n?\s*([^\n]+)", page_text, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def author(req: AuthorRequest) -> AuthorAction:
    ops = [atomic for op in _plan(req) for atomic in _expand(op, req)]
    done = sum(1 for h in req.history if h.get("result") == "ok")
    # The session opens the start URL itself (history[0]); a first "go to" line is that step.
    if not (ops and ops[0]["op"] == "navigate"):
        done -= 1
    if done >= len(ops):
        lines = [_BULLET.sub("", line).strip() for line in req.instructions.splitlines()]
        # Name it after the first real task line (not "go to …" or "log in …").
        name = next(
            (
                line
                for line in lines
                if line and not re.match(r"(?i)(go to|open|navigate|visit|log ?in|sign in)\b", line)
            ),
            "",
        )
        return _action(
            status="done", workflow_name=(name or "Task from instructions")[:80],
            summary="Follows the given instructions.", explanation="All instructions are done.",
        )  # fmt: skip
    op, c = ops[max(done, 0)], req.candidates
    kind = op["op"]
    if kind == "navigate":
        return _action(action="navigate", url=op["url"], intent=f"Open {op['url']}")
    if kind == "fill_secret":
        target = _best(c, op["find"], ("textbox", "input")) or _best(c, op["find"])
        return _action(
            action="fill", candidate_id=target, intent=f"Enter the {op['field']}",
            value_kind="secret", secret_name=op["secret"], secret_field=op["field"],
        )  # fmt: skip
    if kind == "fill":
        return _action(
            action="fill", candidate_id=_best(c, op["field"]), intent=f"Enter the {op['field']}",
            value_kind="input", value=op["value"], input_name=re.sub(r"[^a-z0-9]+", "_", op["field"].lower()).strip("_") or "value",
            input_type="number" if re.fullmatch(r"-?[\d,]+(\.\d+)?", op["value"]) else "string",
        )  # fmt: skip
    if kind == "select":
        return _action(
            action="select", candidate_id=_best(c, op["field"]), intent=f"Choose the {op['field']}",
            value_kind="input", value=op["value"], input_name=re.sub(r"[^a-z0-9]+", "_", op["field"].lower()).strip("_") or "choice",
            input_type="string",
        )  # fmt: skip
    if kind in ("check", "uncheck"):
        return _action(
            action=kind,
            candidate_id=_best(c, op["field"]),
            intent=f"{kind.capitalize()} {op['field']}",
        )
    if kind == "press":
        return _action(action="press", key=op["key"], intent=f"Press {op['key']}")
    if kind == "click":
        target = _best(c, op["name"])
        name = next(
            (x.get("name") or x.get("text") or "" for x in c if x["id"] == target), op["name"]
        )
        return _action(
            action="click", candidate_id=target, intent=f"Click {name or op['name']}",
            risky=bool(_RISKY.search(name or op["name"])),
        )  # fmt: skip
    if kind == "wait":
        return _action(action="wait_for", wait_text=op["text"], intent=f"Wait for “{op['text']}”")
    value = _value_after(req.page_text, op["label"])
    if not value:
        return _action(status="stuck", explanation=f"Couldn't find “{op['label']}” on the page.")
    number = re.search(r"-?[\d,]+(\.\d+)?", value)
    return _action(
        action="extract", intent=f"Read the {op['label']}", value=value, output_name=op["name"],
        output_type="number" if number and number.group(0) == value else "string",
    )  # fmt: skip
