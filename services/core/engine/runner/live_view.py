"""What the live view shows: a moving pointer before each action, and a real-time screencast.

Both are best effort. A failure here only makes the live view poorer; it never fails a run.
"""

import contextlib
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from playwright.sync_api import BrowserContext, Locator, Page
from playwright.sync_api import Error as PlaywrightError

log = logging.getLogger(__name__)

CURSOR_JS = (Path(__file__).parent / "static" / "cursor.js").read_text(encoding="utf-8")
GLIDE_MS = 380  # matches the pointer's CSS transition, so the screencast catches the move


def install_cursor(context: BrowserContext) -> None:
    with contextlib.suppress(PlaywrightError):
        context.add_init_script(CURSOR_JS)


def point_at(page: Page, locator: Locator, *, click: bool = False) -> None:
    """Glide the pointer to the element's centre (and ripple for a click)."""
    try:
        locator.scroll_into_view_if_needed(timeout=2000)
        box = locator.bounding_box(timeout=2000)
        if not box:
            return
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        page.evaluate(
            "([x, y, c]) => { if (!window.__woCursor) return; c ? __woCursor.click(x, y) : __woCursor.move(x, y); }",
            [x, y, click],
        )
        page.wait_for_timeout(GLIDE_MS)
    except PlaywrightError:
        pass


class Screencast:
    """Chromium's screencast of one page, throttled, sent as ``frame`` events.

    Frames arrive whenever Playwright is waiting on the page (actions, waits), which is when
    something is happening; a still page sends nothing.
    """

    def __init__(
        self, page: Page, publish: Callable[[dict[str, Any]], None], *, fps: float = 4.0
    ) -> None:
        self.publish = publish
        self.min_gap = 1.0 / fps
        self.last = 0.0
        self.step_id = ""
        self.session = None
        try:
            self.session = page.context.new_cdp_session(page)
            self.session.on("Page.screencastFrame", self._on_frame)
            self.session.send(
                "Page.startScreencast",
                {"format": "jpeg", "quality": 55, "maxWidth": 1280, "maxHeight": 800},
            )
        except PlaywrightError as exc:
            log.info("screencast unavailable: %s", str(exc).splitlines()[0])
            self.session = None

    def _on_frame(self, params: dict[str, Any]) -> None:
        with contextlib.suppress(PlaywrightError):
            if self.session is not None:
                self.session.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})
        now = time.monotonic()
        if now - self.last < self.min_gap:
            return
        self.last = now
        self.publish({"type": "frame", "step_id": self.step_id, "jpeg_b64": params["data"]})

    def stop(self) -> None:
        if self.session is None:
            return
        with contextlib.suppress(PlaywrightError):
            self.session.send("Page.stopScreencast")
            self.session.detach()
        self.session = None
