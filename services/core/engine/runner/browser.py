"""One Chromium per worker process; every run gets a fresh context (docs/08 "Isolation").

Playwright's sync API keeps an asyncio loop running in this thread to drive the browser,
which makes Django refuse ORM calls ("async context"). The runner process is genuinely
synchronous, so it opts out of that guard; only run workers import this module.
"""

import atexit
import os

from playwright.sync_api import Browser, Playwright, sync_playwright

_playwright: Playwright | None = None
_browser: Browser | None = None


def get_browser() -> Browser:
    global _playwright, _browser
    if _browser is not None and _browser.is_connected():
        return _browser
    if _playwright is None:
        os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
        _playwright = sync_playwright().start()
    _browser = _playwright.chromium.launch(headless=True)
    return _browser


@atexit.register
def _shutdown() -> None:
    global _playwright, _browser
    try:
        if _browser is not None:
            _browser.close()
        if _playwright is not None:
            _playwright.stop()
    except Exception:  # noqa: S110 - best effort at interpreter exit
        pass
    _browser = _playwright = None
