import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from engine.compiler.normalize import normalize
from engine.compiler.recording import Recording

FIXTURES = Path(__file__).parent / "fixtures"
PAGE = "http://acme.test/invoices/new"


def el(css: str, *, tag: str = "button", role: str | None = "button", name: str | None = None,
       text: str | None = None, **extra: Any) -> dict[str, Any]:  # fmt: skip
    return {
        "tag": tag,
        "role": role,
        "accessible_name": name,
        "text": text if text is not None else name,
        "css_path": css,
        "xpath": f"/html/body/{tag}",
        "is_unique": {"css": True, "role_name": True, "label": True, "text": True},
        **extra,
    }


FIELD = el("#amount", tag="input", role="textbox", name="Amount", text=None, label_text="Amount")


class Rec:
    """Builds a raw recording event by event, with increasing seq and ts."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.ts = 1_000

    def add(self, type_: str, element: dict | None = None, *, url: str = PAGE, gap: int = 1000,
            **extra: Any) -> "Rec":  # fmt: skip
        self.ts += gap
        self.events.append({
            "seq": len(self.events) + 1, "ts": self.ts, "type": type_, "url": url,
            "frame_path": [], "element": element, "value": None, "value_masked": False,
            "frame_ref": f"frames/{len(self.events) + 1:04d}.webp" if element else None, **extra,
        })  # fmt: skip
        return self

    def nav(self, url: str, gap: int = 300, transition: str = "link_or_script") -> "Rec":
        return self.add("navigate", url=url, gap=gap, nav={"transition": transition})

    def run(self) -> dict[str, Any]:
        return normalize(Recording.model_validate({"format_version": 1, "events": self.events}))


def actions(result: dict[str, Any]) -> list[str]:
    return [c["action"] for c in result["candidates"]]


def start() -> Rec:
    return Rec().nav(PAGE, transition="initial")


def test_typing_in_one_field_becomes_one_fill_with_the_final_value() -> None:
    result = (
        start()
        .add("click", FIELD)
        .add("input", FIELD, value="12")
        .add("input", FIELD, value="1250.50")
        .run()
    )
    assert actions(result) == ["navigate", "fill"]
    fill = result["candidates"][1]
    assert fill["value"] == "1250.50"
    assert fill["frame_ref"] == "frames/0002.webp"  # the screenshot from before the click
    assert fill["source_seqs"] == [2, 3, 4]
    assert result["stats"]["dropped"] == {"focus_click": 1, "merged_typing": 1}


def test_masked_values_stay_masked() -> None:
    pw = el("#pw", tag="input", role="textbox", name="Password", label_text="Password")
    result = start().add("input", pw, value="__SECRET__", value_masked=True).run()
    assert result["candidates"][1]["value"] == "__SECRET__"
    assert result["candidates"][1]["value_masked"] is True


def test_typed_then_cleared_is_dropped_but_a_plain_clear_is_kept() -> None:
    other = el("#notes", tag="textarea", role="textbox", name="Notes")
    result = (
        start()
        .add("input", FIELD, value="oops")
        .add("input", FIELD, value="")
        .add("input", other, value="")
        .run()
    )
    assert actions(result) == ["navigate", "fill"]
    assert result["candidates"][1]["target"]["locators"][0]["name"] == "Notes"
    assert result["stats"]["dropped"]["typed_then_cleared"] == 1


def test_typing_into_two_fields_stays_two_fills() -> None:
    other = el("#due", tag="input", role="textbox", name="Due date")
    result = (
        start()
        .add("input", FIELD, value="5")
        .add("input", other, value="x")
        .add("input", FIELD, value="6")
        .run()
    )
    assert actions(result) == ["navigate", "fill", "fill", "fill"]


def test_repeated_and_double_clicks_collapse() -> None:
    save = el("#save", name="Save")
    result = (
        start()
        .add("click", save)
        .add("click", save, gap=120)
        .add("dblclick", save, gap=10)
        .add("click", save, gap=2000)  # a deliberate second click later is kept
        .run()
    )
    assert actions(result) == ["navigate", "click", "click"]
    assert result["candidates"][1]["notes"] == ["double_click"]
    assert result["stats"]["dropped"]["repeated_click"] == 2


def test_click_that_navigates_owns_the_navigation_and_redirects_collapse() -> None:
    link = el("#inv", tag="a", role="link", name="Invoices")
    result = (
        start()
        .add("click", link)
        .nav("http://acme.test/invoices?page=1")
        .nav("http://acme.test/invoices", gap=50)
        .run()
    )
    assert actions(result) == ["navigate", "click"]
    assert result["candidates"][1]["navigates_to"] == "http://acme.test/invoices"


def test_navigation_without_a_cause_is_a_navigate_step() -> None:
    result = (
        start()
        .add("click", el("#x", name="Refresh"))
        .nav("http://acme.test/vendors", gap=30_000)  # typed in the address bar much later
        .run()
    )
    assert actions(result) == ["navigate", "click", "navigate"]
    assert result["candidates"][2]["url"] == "http://acme.test/vendors"


def test_fragment_only_navigation_is_dropped() -> None:
    result = start().nav(PAGE + "#details", gap=20_000).run()
    assert actions(result) == ["navigate"]
    assert result["stats"]["dropped"] == {"same_page_navigation": 1}


def test_missing_initial_navigation_is_synthesized() -> None:
    result = normalize(
        Recording.model_validate(
            {
                "format_version": 1,
                "recording": {"startUrl": PAGE},
                "events": Rec().add("click", el("#save", name="Save")).events,
            }
        )
    )
    assert actions(result) == ["navigate", "click"]
    assert result["candidates"][0]["notes"] == ["synthesized_start"]
    assert result["start_url"] == PAGE


def test_native_select_and_checkbox_clicks_fold_into_their_step() -> None:
    select = el("#status", tag="select", role="combobox", name="Status")
    box = el("#urgent", tag="input", role="checkbox", name="Urgent")
    result = (
        start()
        .add("click", select)
        .add("select", select, value="open", option_label="Open")
        .add("click", box)
        .add("check", box)
        .run()
    )
    assert actions(result) == ["navigate", "select", "check"]
    assert result["candidates"][1]["value"] == "open"
    assert result["candidates"][1]["option_label"] == "Open"


def test_custom_dropdown_becomes_select_by_label() -> None:
    combo = el("#vendor", role="combobox", name="Vendor")
    option = el("#opt-3", tag="li", role="option", name="Northwind Ltd")
    result = start().add("click", combo).add("click", option).run()
    assert actions(result) == ["navigate", "select"]
    step = result["candidates"][1]
    assert step["option_label"] == "Northwind Ltd"
    assert step["notes"] == ["custom_dropdown"]
    assert step["target"]["locators"][0] == {
        "kind": "role",
        "role": "combobox",
        "name": "Vendor",
        "exact": True,
    }
    assert step["option_target"]["locators"][0]["name"] == "Northwind Ltd"
    assert "value" not in step


def test_container_clicks_are_noise_but_short_clickable_divs_are_kept() -> None:
    form = el("#form > div", tag="div", role=None, name=None, text="Supplier Amount Due date " * 5)
    card = el("#card", tag="div", role=None, name=None, text="Open report")
    result = start().add("click", form).add("click", card).run()
    assert actions(result) == ["navigate", "click"]
    assert result["candidates"][1]["element"]["text"] == "Open report"
    assert result["stats"]["dropped"] == {"noise_click": 1}


def test_submit_events_and_tab_presses_are_dropped_enter_is_kept() -> None:
    result = (
        start()
        .add("input", FIELD, value="5")
        .add("press", FIELD, key="Tab")
        .add("press", FIELD, key="Enter")
        .add("submit", el("form", tag="form", role="form"))
        .nav("http://acme.test/invoices/INV-1")
        .run()
    )
    assert actions(result) == ["navigate", "fill", "press"]
    assert result["candidates"][2]["key"] == "Enter"
    assert result["candidates"][2]["navigates_to"] == "http://acme.test/invoices/INV-1"


def test_warnings_are_collected_and_unsupported_events_dropped() -> None:
    result = (
        start()
        .add(
            "file_input",
            el("#f", tag="input", role=None),
            warning="File uploads can't be replayed.",
        )
        .run()
    )
    assert actions(result) == ["navigate"]
    assert result["warnings"] == ["File uploads can't be replayed."]


def test_unknown_format_version_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Recording.model_validate({"format_version": 2, "events": []})


def test_real_recording_acme_v2() -> None:
    """Recorded by hand in Chrome on the v2 portal variant (Day 4 manual test)."""
    raw = json.loads((FIXTURES / "acme_v2_create_invoice.json").read_text(encoding="utf-8"))
    result = normalize(Recording.model_validate(raw))
    summary = [
        (c["action"], (c.get("element") or {}).get("name"), c.get("value") or c.get("option_label"))
        for c in result["candidates"]
    ]
    assert summary == [
        ("navigate", None, None),
        ("fill", "User ID", "sara"),
        ("fill", "Password", "__SECRET__"),
        ("click", "Log in", None),
        ("click", "Invoices", None),
        ("click", "Create invoice", None),
        ("select", "Supplier", "City Power & Light"),
        ("fill", "Invoice amount", "234"),
        ("fill", "Payment due date", "12/03/2024"),
        ("fill", "Notes", "automation"),
        ("click", "Submit for approval", None),
        ("click", "Dashboard", None),
    ]
    assert result["stats"]["raw_events"] == 29
    assert result["candidates"][10]["navigates_to"].startswith(
        "http://localhost:3001/invoices/INV-"
    )
    assert "acme-demo" not in json.dumps(result)
