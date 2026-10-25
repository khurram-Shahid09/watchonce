"""Turn spec locators into Playwright locators and find the step's element
(docs/08 "Step execution", rungs L0/L1 of the self-healing ladder).

A locator only counts if it resolves to exactly one visible element. They are tried in
order, repeatedly, until the step's timeout: pages render late, and an earlier (more
robust) locator that appears a moment later is still preferred on the next pass.
"""

import time
from dataclasses import dataclass
from typing import Any

from playwright.sync_api import Locator, Page

POLL_S = 0.25


class ElementNotFound(Exception):
    def __init__(self, tried: list[dict[str, Any]], counts: list[int]):
        self.tried = tried
        self.counts = counts
        detail = ", ".join(f"{loc['kind']}={n}" for loc, n in zip(tried, counts, strict=False))
        super().__init__(f"No locator matched exactly one visible element ({detail}).")


@dataclass
class Found:
    locator: Locator
    index: int  # position in target.locators
    spec: dict[str, Any]

    @property
    def rung(self) -> str:
        return "L0" if self.index == 0 else "L1"


def to_playwright(page: Page, loc: dict[str, Any]) -> Locator:
    kind = loc["kind"]
    exact = loc.get("exact", False)
    if kind == "testid":
        return page.get_by_test_id(loc["value"])
    if kind == "role":
        name = loc.get("name")
        return (
            page.get_by_role(loc["role"], name=name, exact=exact)
            if name
            else page.get_by_role(loc["role"])
        )
    if kind == "label":
        return page.get_by_label(loc["value"], exact=exact)
    if kind == "placeholder":
        return page.get_by_placeholder(loc["value"], exact=exact)
    if kind == "text":
        return page.get_by_text(loc["value"], exact=exact)
    if kind == "css":
        return page.locator(loc["value"])
    if kind == "xpath":
        return page.locator(f"xpath={loc['value']}")
    raise ValueError(f"unknown locator kind {kind!r}")


def _visible(candidate: Locator) -> Locator:
    return candidate.filter(visible=True)


def _count(candidate: Locator) -> int:
    try:
        return _visible(candidate).count()
    except Exception:  # a selector this page can't evaluate counts as no match
        return 0


def find(page: Page, locators: list[dict[str, Any]], timeout_ms: int) -> Found:
    deadline = time.monotonic() + timeout_ms / 1000
    counts = [0] * len(locators)
    while True:
        for index, spec in enumerate(locators):
            candidate = to_playwright(page, spec)
            counts[index] = _count(candidate)
            if counts[index] == 1:
                return Found(_visible(candidate), index, spec)
        if time.monotonic() >= deadline:
            raise ElementNotFound(locators, counts)
        page.wait_for_timeout(POLL_S * 1000)  # keeps Playwright processing page events
