"""Playwright I/O for meteoblue. Returns rendered HTML and a JPEG screenshot.

This module is the only one with browser side effects. parse.py / caption.py
work entirely on its outputs.
"""
from playwright.sync_api import Page, sync_playwright

# Units we force on every fetch so output is independent of the runner's
# geo-IP. meteoblue persists each click in the `mb` session cookie.
_UNITS = ("CELSIUS", "KNOT", "MILLIMETER")


def _dismiss_banner(page: Page) -> None:
    """Remove the GDPR/consent overlay if present (it blocks clicks)."""
    page.evaluate(
        "document.querySelectorAll('.fc-consent-root').forEach(e => e.remove())"
    )


def _force_unit(page: Page, data_unit: str) -> None:
    """Open the settings menu and click the unit anchor for `data_unit`.

    The click navigates back to the same URL with the preference saved in the
    `mb` session cookie. Caller must dismiss the banner again afterwards.
    """
    page.locator("#settings").click()
    page.locator(f'a.unit[data-unit="{data_unit}"]').click()
    page.wait_for_load_state("networkidle")


def fetch(url: str) -> tuple[str, bytes]:
    """Open URL, force metric units, toggle to 1h view, screenshot the table.

    Returns (rendered_html, jpeg_bytes). Raises if the toggle or table never
    appears within 5 seconds (treated as a meteoblue layout change).
    """
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        try:
            page = context.new_page()
            page.goto(url, wait_until="networkidle")
            _dismiss_banner(page)

            for unit in _UNITS:
                _force_unit(page, unit)
                _dismiss_banner(page)

            page.locator("label.switch-with-label").first.click()
            page.locator("table.hourlywind").wait_for(state="visible", timeout=5000)
            html = page.content()
            jpeg = page.locator("table.hourlywind").screenshot(
                type="jpeg", quality=90
            )
            return html, jpeg
        finally:
            context.close()
            browser.close()
