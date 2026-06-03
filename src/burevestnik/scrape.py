"""Playwright I/O for meteoblue. Returns rendered HTML and a JPEG screenshot.

This module is the only one with browser side effects. parse.py / caption.py
work entirely on its outputs.
"""
from playwright.sync_api import sync_playwright

# meteoblue stores each unit preference in its own cookie (keyed by the
# `data-type` attribute on the unit anchors in the settings menu). Pre-seeding
# the cookies lets us skip the click-through-the-settings-menu dance and avoids
# losing query strings like ?day=2 to the unit anchors' bare-URL href.
_UNIT_COOKIES = (
    {"name": "temp", "value": "CELSIUS"},
    {"name": "speed", "value": "KNOT"},
    {"name": "precip", "value": "MILLIMETER"},
)
_COOKIE_DOMAIN = "www.meteoblue.com"


# The GDPR/consent overlay (Google Funding Choices, `.fc-consent-root`) blocks
# clicks and covers the screenshot. It is injected by a third-party script that
# loads ~1s *after* domcontentloaded, so a one-shot removal right after goto
# races it and usually fires before the banner exists — the intermittent "modal
# covers the screenshot" bug. Instead, install a MutationObserver as a context
# init script (runs before page scripts on every navigation) that deletes the
# overlay the instant it is added, no matter when that happens. We observe
# `document.documentElement`, falling back to `document` because documentElement
# is still null this early (readyState === "loading") and observing null throws.
_HIDE_CONSENT_SCRIPT = """
(() => {
  const kill = () =>
    document.querySelectorAll('.fc-consent-root').forEach(e => e.remove());
  kill();
  new MutationObserver(kill).observe(document.documentElement || document, {
    childList: true,
    subtree: true,
  });
})();
"""


def fetch(url: str) -> tuple[str, bytes]:
    """Open URL, force metric units via cookies, toggle 1h view, screenshot.

    Returns (rendered_html, jpeg_bytes). Raises if the toggle or table never
    appears within 5 seconds (treated as a meteoblue layout change).
    """
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        try:
            context.add_cookies(
                [{**c, "domain": _COOKIE_DOMAIN, "path": "/"} for c in _UNIT_COOKIES]
            )
            context.add_init_script(_HIDE_CONSENT_SCRIPT)
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded")

            page.locator("label.switch-with-label").first.click()
            page.locator("table.hourlywind").wait_for(state="visible", timeout=5000)
            # The UV-index / celestial-bodies block hydrates separately from the
            # hourly table, so table visibility doesn't guarantee it's in the DOM
            # yet — snapshotting too early drops it and makes parse_uv fail
            # intermittently. Wait for it (attached, not visible: parse.py reads
            # whichever responsive copy comes first in document order, which may
            # be the CSS-hidden one).
            page.locator("div.uv-index").first.wait_for(state="attached", timeout=5000)
            # The init-script observer removes the consent overlay asynchronously;
            # assert it's actually gone before we screenshot. Resolves immediately
            # if the banner never appeared, and raises (instead of silently posting
            # a covered table) if a future meteoblue/vendor change defeats removal.
            page.locator(".fc-consent-root").wait_for(state="detached", timeout=5000)
            html = page.content()
            jpeg = page.locator("table.hourlywind").screenshot(
                type="jpeg", quality=90
            )
            return html, jpeg
        finally:
            context.close()
            browser.close()
