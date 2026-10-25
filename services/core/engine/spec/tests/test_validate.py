import copy
import json
from pathlib import Path

import pytest

from engine.spec import validate_spec
from engine.spec.validate import SCHEMA_PATH, host_allowed

EXAMPLES = SCHEMA_PATH.parent / "examples"
VALID_EXAMPLES = sorted(EXAMPLES.glob("*.json"))
INVALID_CASES = json.loads((EXAMPLES / "invalid" / "cases.json").read_text(encoding="utf8"))[
    "cases"
]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf8"))


@pytest.fixture
def spec() -> dict:
    return copy.deepcopy(load(EXAMPLES / "acme-create-invoice.json"))


def messages(result) -> list[str]:
    return [f"{i.path}: {i.message}" for i in result.errors]


@pytest.mark.parametrize("path", VALID_EXAMPLES, ids=lambda p: p.name)
def test_examples_are_valid(path: Path) -> None:
    result = validate_spec(load(path))
    assert result.ok, messages(result)
    assert result.spec is not None
    assert result.spec.steps


@pytest.mark.parametrize("case", INVALID_CASES, ids=lambda c: c["name"])
def test_schema_rejects_known_bad(spec: dict, case: dict) -> None:
    spec.update(case["set"])
    result = validate_spec(spec)
    assert not result.ok
    assert result.spec is None


def test_example_typed_model(spec: dict) -> None:
    model = validate_spec(spec).spec
    assert model is not None
    submit = next(s for s in model.steps if s.id == "s10")
    assert submit.checkpoint is not None and submit.checkpoint.type == "approval"
    assert [i.name for i in model.inputs] == ["vendor_name", "amount", "due_date"]


def test_unknown_input_reference(spec: dict) -> None:
    spec["steps"][7]["value"] = "{{amount_usd}}"
    assert messages(validate_spec(spec)) == ['steps/7/value: unknown input "amount_usd"']


def test_unknown_secret_field(spec: dict) -> None:
    spec["steps"][1]["value"] = "{{secrets.acme_login.email}}"
    assert messages(validate_spec(spec)) == ['steps/1/value: unknown secret "acme_login.email"']


def test_unsupported_filter(spec: dict) -> None:
    spec["steps"][7]["value"] = "{{amount | upper}}"
    assert "unsupported filter" in messages(validate_spec(spec))[0]


def test_output_used_before_extract(spec: dict) -> None:
    spec["steps"][7]["value"] = "{{outputs.invoice_number}}"
    assert messages(validate_spec(spec)) == [
        'steps/7/value: output "invoice_number" is used before it is extracted'
    ]


def test_declared_output_never_extracted(spec: dict) -> None:
    spec["outputs"].append({"name": "vendor_id", "type": "string"})
    assert messages(validate_spec(spec)) == ['outputs/1: output "vendor_id" is never extracted']


def test_output_extracted_twice(spec: dict) -> None:
    dup = copy.deepcopy(spec["steps"][-1])
    dup["id"] = "s13"
    spec["steps"].append(dup)
    assert "already produced" in messages(validate_spec(spec))[0]


def test_duplicate_step_ids(spec: dict) -> None:
    spec["steps"][1]["id"] = "s1"
    assert messages(validate_spec(spec)) == ['steps/1/id: duplicate step "s1"']


def test_navigate_outside_allowed_domains(spec: dict) -> None:
    spec["steps"][0]["url"] = "https://evil.example.com/login"
    assert messages(validate_spec(spec)) == [
        'steps/0/url: host "evil.example.com" is not in allowed_domains'
    ]


def test_templated_host_rejected(spec: dict) -> None:
    spec["steps"][0]["url"] = "https://{{vendor_name}}.acme-demo.com/"
    assert "cannot be templated" in messages(validate_spec(spec))[0]


def test_templated_path_allowed(spec: dict) -> None:
    spec["steps"][0]["url"] = "https://portal.acme-demo.com/vendors?q={{vendor_name}}"
    assert validate_spec(spec).ok


def test_secret_in_url_rejected(spec: dict) -> None:
    spec["steps"][0]["url"] = "https://portal.acme-demo.com/login?u={{secrets.acme_login.username}}"
    assert messages(validate_spec(spec)) == ["steps/0/url: secrets cannot be used in URLs"]


def test_risky_step_without_checkpoint_warns(spec: dict) -> None:
    del spec["steps"][9]["checkpoint"]
    result = validate_spec(spec)
    assert result.ok
    assert any("irreversible" in w.message for w in result.warnings)


def test_single_locator_warns(spec: dict) -> None:
    spec["steps"][3]["target"]["locators"] = spec["steps"][3]["target"]["locators"][:1]
    result = validate_spec(spec)
    assert result.ok
    assert [w.path for w in result.warnings] == ["steps/3/target"]


@pytest.mark.parametrize(
    ("netloc", "allowed", "expected"),
    [
        ("portal.acme-demo.com", ["portal.acme-demo.com"], True),
        ("PORTAL.acme-demo.com", ["portal.acme-demo.com"], True),
        ("evil.portal.acme-demo.com", ["portal.acme-demo.com"], False),
        ("cdn.acme-demo.com", ["*.acme-demo.com"], True),
        ("acme-demo.com.evil.io", ["*.acme-demo.com"], False),
        ("localhost:3001", ["localhost:3001"], True),
        ("localhost:3002", ["localhost:3001"], False),
        ("localhost:3002", ["localhost"], True),
    ],
)
def test_host_allowed(netloc: str, allowed: list[str], expected: bool) -> None:
    assert host_allowed(netloc, allowed) is expected
