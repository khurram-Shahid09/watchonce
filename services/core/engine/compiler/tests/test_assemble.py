import json
from pathlib import Path
from typing import Any

import pytest

from engine.compiler.assemble import assemble, check
from engine.compiler.normalize import normalize
from engine.compiler.recording import Recording
from engine.llm.types import (
    InputUnderstanding,
    OutputUnderstanding,
    StepUnderstanding,
    Understanding,
    ValueSource,
)
from engine.spec.validate import validate_spec

FIXTURE = Path(__file__).parent / "fixtures" / "acme_v2_create_invoice.json"


@pytest.fixture(scope="module")
def candidates() -> list[dict[str, Any]]:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return normalize(Recording.model_validate(raw))["candidates"]


def src(kind: str = "none", name: str = "", secret: str = "", field: str = "") -> ValueSource:
    return ValueSource(kind=kind, input_name=name, secret_name=secret, secret_field=field)  # type: ignore[arg-type]


def step(cid: str, intent: str, source: ValueSource | None = None, **kw: Any) -> StepUnderstanding:
    defaults: dict[str, Any] = {
        "keep": True,
        "drop_reason": "",
        "checkpoint": False,
        "checkpoint_reason": "",
        "assert_text_after": "",
    }
    return StepUnderstanding(
        candidate_id=cid, intent=intent, value_source=source or src(), **{**defaults, **kw}
    )


def good_answer() -> Understanding:
    """What a careful model answers for the v2 portal recording (c1..c12)."""
    return Understanding(
        workflow_name="Create vendor invoice in Acme Portal",
        summary="Creates an invoice for a supplier and submits it for approval.",
        steps=[
            step("c1", "Open the portal login page"),
            step("c2", "Enter the user ID", src("secret", secret="acme_login", field="username")),
            step("c3", "Enter the password", src("secret", secret="acme_login", field="password")),
            step("c4", "Log in"),
            step("c5", "Open the invoices list"),
            step("c6", "Open the new invoice form"),
            step("c7", "Choose the supplier", src("input", "supplier")),
            step("c8", "Enter the invoice amount", src("input", "amount")),
            step("c9", "Enter the payment due date", src("input", "due_date")),
            step("c10", "Enter notes", src("constant")),
            # The model forgot the checkpoint here; assembly must add it anyway.
            step("c11", "Submit the invoice for approval", assert_text_after="Invoice created"),
            step("c12", "Go back to the dashboard", keep=False, drop_reason="after the task"),
        ],
        inputs=[
            InputUnderstanding(
                name="supplier",
                type="string",
                example="City Power & Light",
                description="Supplier",
                format_hint="",
            ),
            InputUnderstanding(
                name="amount",
                type="number",
                example="234",
                description="Amount in USD",
                format_hint="",
            ),
            InputUnderstanding(
                name="due_date",
                type="date",
                example="2024-12-03",
                description="Due date",
                format_hint="MM/DD/YYYY",
            ),
            InputUnderstanding(
                name="unused",
                type="string",
                example="x",
                description="never referenced",
                format_hint="",
            ),
        ],  # fmt: skip
        outputs=[
            OutputUnderstanding(
                name="invoice_number",
                type="string",
                description="Read the new invoice number",
                after_candidate_id="c11",
                from_candidate_id="",
                pattern=r"INV-\d+",
            )
        ],
        warnings=[],
    )


def test_good_answer_assembles_into_a_valid_spec(candidates) -> None:
    u = good_answer()
    assert check(candidates, u) == []
    spec, warnings = assemble(candidates, u, recording_id="rec_1", compiled_by="test:model")

    result = validate_spec(spec)
    assert result.ok, result.errors
    steps = spec["steps"]
    assert [s["action"] for s in steps] == [
        "navigate", "fill", "fill", "click", "click", "click",
        "select", "fill", "fill", "fill", "click", "extract",
    ]  # fmt: skip
    by_intent = {s["intent"]: s for s in steps}

    assert by_intent["Enter the password"]["value"] == "{{secrets.acme_login.password}}"
    assert by_intent["Choose the supplier"]["label"] == "{{supplier}}"
    assert by_intent["Enter the invoice amount"]["value"] == "{{amount}}"  # recorded "234"
    assert by_intent["Enter the payment due date"]["value"] == '{{due_date | date:"MM/DD/YYYY"}}'
    assert by_intent["Enter notes"]["value"] == "automation"  # constant: replayed as recorded

    submit = by_intent["Submit the invoice for approval"]
    assert submit["checkpoint"]["type"] == "approval"  # forced by the risky verb
    assert submit["assert_after"] == {"type": "text_visible", "value": "Invoice created"}
    assert by_intent["Log in"]["assert_after"] == {"type": "url_matches", "value": "/dashboard"}

    extract = steps[-1]
    assert extract["output"] == "invoice_number" and extract["pattern"] == r"INV-\d+"
    assert extract["target"] == {"locators": [{"kind": "css", "value": "body"}]}
    assert steps.index(extract) == steps.index(submit) + 1

    assert [i["name"] for i in spec["inputs"]] == [
        "supplier",
        "amount",
        "due_date",
    ]  # unused dropped
    assert spec["inputs"][1]["example"] == 234.0
    assert spec["secrets"] == [{"name": "acme_login", "fields": ["username", "password"]}]
    assert spec["allowed_domains"] == ["localhost:3001"]
    assert spec["start_url"] == "http://localhost:3001/login"
    assert spec["source"]["compiled_by"] == "test:model"
    assert [s["id"] for s in steps] == [f"s{n}" for n in range(1, 13)]
    assert any("c12" in w for w in warnings)
    assert "sara" not in json.dumps(spec)  # the user ID became a secret reference


def test_masked_value_is_always_a_secret(candidates) -> None:
    u = good_answer()
    u.steps[2] = step("c3", "Enter the password", src("constant"))
    assert any("masked" in p for p in check(candidates, u))


def test_check_reports_unusable_answers(candidates) -> None:
    u = good_answer()
    u.steps = u.steps[:-1]  # c12 missing
    assert check(candidates, u) == ["steps is missing candidates c12"]

    u = good_answer()
    u.steps[6] = step("c7", "Choose the supplier", src("input", "vendor"))
    u.steps[0] = step("c1", "Open", keep=False)
    u.inputs.append(
        InputUnderstanding(
            name="Bad Name", type="string", example="", description="", format_hint=""
        )
    )
    u.outputs[0].pattern = "INV-("
    problems = check(candidates, u)
    assert 'c7: input "vendor" is not declared in inputs' in problems
    assert "c1 (the first navigation) must be kept" in problems
    assert any("snake_case" in p for p in problems)
    assert any("not a valid regular expression" in p for p in problems)


def test_decimal_amounts_keep_their_precision(candidates) -> None:
    c = [dict(x) for x in candidates]
    c[7] = {**c[7], "value": "1250.50"}
    spec, _ = assemble(c, good_answer(), recording_id="rec_1", compiled_by="t")
    assert spec["steps"][7]["value"] == "{{amount | number:2}}"
