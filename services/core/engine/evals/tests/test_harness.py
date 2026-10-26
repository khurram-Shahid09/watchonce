from typing import Any

from engine.evals.harness import align, replay_inputs, step_name, uses_input


def step(action: str, name: str | None = None, **extra) -> dict:
    target = {"fingerprint": {"accessible_name": name}, "locators": []} if name else {}
    return {"id": "s", "action": action, "target": target, **extra}


def test_align_skips_extra_and_missing_steps() -> None:
    expected: list[list[Any]] = [["navigate", None], ["fill", "Amount"], ["click", "Submit"]]
    steps = [
        step("navigate"),
        step("click", "Help"),
        step("fill", "amount"),
        step("click", "Submit"),
    ]
    assert align(expected, steps) == [(0, 0), (1, 2), (2, 3)]


def test_step_name_falls_back_to_locators() -> None:
    s = {"action": "fill", "target": {"locators": [{"kind": "label", "value": "Due date"}]}}
    assert step_name(s) == "Due date"
    assert step_name(step("navigate")) is None


def test_inputs_come_from_the_replay_values_by_field() -> None:
    spec: dict[str, Any] = {
        "steps": [
            step("fill", "Username", value="{{secrets.app_login.username}}"),
            step("fill", "Amount", value="{{amount | number:2}}"),
            step("fill", "Notes", value="{{notes}}"),
        ],
        "inputs": [
            {"name": "amount", "type": "number", "example": 5},
            {"name": "notes", "type": "string", "example": "seen"},
        ],
    }
    assert not uses_input(spec["steps"][0]) and uses_input(spec["steps"][1])
    assert replay_inputs(spec, {"Amount": "77.25"}) == {"amount": 77.25, "notes": "seen"}
