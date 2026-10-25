from typing import Any

from engine.compiler.locators import build_fingerprint, build_locators, build_target
from engine.compiler.recording import Element
from engine.spec.models import Target


def element(**overrides: Any) -> Element:
    data: dict[str, Any] = {
        "tag": "button",
        "role": "button",
        "accessible_name": "New invoice",
        "text": "New invoice",
        "id": "btn-new",
        "classes": ["btn", "btn-primary"],
        "attrs": {"data-testid": "new-invoice", "type": "button", "placeholder": None},
        "label_text": None,
        "css_path": "#btn-new",
        "xpath": "/html/body/div[1]/button[2]",
        "bbox": [100, 50, 200, 40],
        "viewport": [1000, 500],
        "nearby_text": ["Invoices"],
        "is_unique": {"testid": True, "role_name": True, "text": True, "css": True, "label": None},
    }
    data.update(overrides)
    return Element.model_validate(data)


def kinds(locators: list[dict]) -> list[str]:
    return [loc["kind"] for loc in locators]


def test_order_is_most_robust_first() -> None:
    locators = build_locators(element())
    assert kinds(locators) == ["testid", "role", "text", "css", "xpath"]
    assert locators[0] == {"kind": "testid", "value": "new-invoice"}
    assert locators[1] == {"kind": "role", "role": "button", "name": "New invoice", "exact": True}


def test_form_field_uses_label_and_placeholder_not_typed_text() -> None:
    field = element(
        tag="input",
        role="textbox",
        accessible_name="Due date",
        text="12/03/2024",
        label_text="Due date",
        attrs={"name": "due", "placeholder": "MM/DD/YYYY"},
        css_path='input[name="due"]',
        is_unique={"role_name": True, "label": True, "text": True, "css": True},
    )
    assert kinds(build_locators(field)) == ["role", "label", "placeholder", "css", "xpath"]


def test_non_unique_locators_are_left_out() -> None:
    ambiguous = element(
        attrs={"data-testid": "row-delete"},
        accessible_name="Delete",
        text="Delete",
        css_path="ul > li:nth-of-type(2) > button",
        is_unique={"testid": False, "role_name": False, "text": False, "css": True},
    )
    assert kinds(build_locators(ambiguous)) == ["css", "xpath"]


def test_other_test_attributes_become_css_selectors() -> None:
    locators = build_locators(element(attrs={"data-qa": 'save "draft"'}))
    assert locators[0] == {"kind": "css", "value": '[data-qa="save \\"draft\\""]'}


def test_long_names_and_text_are_skipped() -> None:
    long = "Lorem ipsum " * 10
    locators = build_locators(element(attrs={}, accessible_name=long, text=long))
    assert kinds(locators) == ["css", "xpath"]


def test_shadow_dom_drops_xpath_and_something_always_remains() -> None:
    inner = element(
        attrs={},
        accessible_name=None,
        text=None,
        css_path="#inner",
        shadow_hosts=["#widget"],
        is_unique={"css": False},
    )
    assert build_locators(inner) == [{"kind": "css", "value": "#inner"}]


def test_fingerprint_normalizes_bbox_and_keeps_stable_attributes() -> None:
    fp = build_fingerprint(element(), ["iframe#pay"])
    assert fp["bbox_norm"] == [0.1, 0.1, 0.2, 0.08]
    assert fp["attributes"] == {
        "data-testid": "new-invoice",
        "type": "button",
        "id": "btn-new",
        "class": "btn btn-primary",
    }
    assert fp["frame_path"] == ["iframe#pay"]


def test_target_is_valid_for_the_workflow_spec() -> None:
    Target.model_validate(build_target(element(), []))
    Target.model_validate(build_target(element(viewport=[0, 0]), []))  # no bbox_norm
