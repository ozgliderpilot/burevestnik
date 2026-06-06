"""Playwright I/O for meteoblue. Returns rendered HTML and a JPEG screenshot.

This module is the only one with browser side effects. parse.py / caption.py
work entirely on its outputs.
"""
from contextlib import contextmanager

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

# Vertical crop of the meteogram element, as fractions of its height, keeping
# just the temperature panel: from below the "Melbourne CBD"/logo title band
# (TOP) down to below the temperature panel's hour-tick row, before the
# precipitation panel (BOTTOM). The clouds + wind panels are dropped. Tuned
# against a live 650px render — see the crop sample under docs/superpowers/specs.
_TEMP_PANEL_TOP_FRACTION = 0.10
_TEMP_PANEL_BOTTOM_FRACTION = 0.42


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


@contextmanager
def _browser_page():
    """Yield a Playwright page with metric-unit cookies + consent killer set.

    Shared by fetch() and fetch_meteogram() so the cookie seeding and the
    consent-overlay MutationObserver init script live in one place.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        try:
            context.add_cookies(
                [{**c, "domain": _COOKIE_DOMAIN, "path": "/"} for c in _UNIT_COOKIES]
            )
            context.add_init_script(_HIDE_CONSENT_SCRIPT)
            yield context.new_page()
        finally:
            context.close()
            browser.close()


def fetch(url: str) -> tuple[str, bytes]:
    """Open URL, force metric units via cookies, toggle 1h view, screenshot.

    Returns (rendered_html, jpeg_bytes). Raises if the toggle or table never
    appears within 5 seconds (treated as a meteoblue layout change).
    """
    with _browser_page() as page:
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
        jpeg = page.locator("table.hourlywind").screenshot(type="jpeg", quality=90)
        return html, jpeg


def fetch_meteogram(url: str) -> tuple[str, bytes]:
    """Open URL, screenshot the meteogram cropped to its temperature panel.

    Returns (rendered_html, jpeg_bytes). The chart (#blooimage) is a JS-hydrated
    Highcharts SVG; we wait for it to render, then clip a full-width band from
    the top of the element down to _TEMP_PANEL_FRACTION of its height. Raises if
    the chart never renders within 15 seconds (treated as a layout change).
    """
    with _browser_page() as page:
        page.goto(url, wait_until="domcontentloaded")

        # The meteogram is lazy-loaded: it only hydrates once scrolled into the
        # viewport, so scroll first, then wait for the Highcharts SVG to render.
        target = page.locator("#blooimage")
        target.scroll_into_view_if_needed()
        page.locator("#blooimage svg.highcharts-root").wait_for(
            state="visible", timeout=15000
        )
        page.locator(".fc-consent-root").wait_for(state="detached", timeout=5000)
        html = page.content()

        box = target.bounding_box()
        if box is None:
            raise RuntimeError("meteogram #blooimage has no bounding box")
        top = box["y"] + box["height"] * _TEMP_PANEL_TOP_FRACTION
        bottom = box["y"] + box["height"] * _TEMP_PANEL_BOTTOM_FRACTION
        clip = {
            "x": box["x"],
            "y": top,
            "width": box["width"],
            "height": bottom - top,
        }
        jpeg = page.screenshot(type="jpeg", quality=90, clip=clip)
        return html, jpeg
