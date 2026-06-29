"""Headless Chrome browser client for JS-rendered (SPA) web pages."""

from __future__ import annotations

import logging
import urllib.parse
from collections.abc import Callable, Generator
from contextlib import contextmanager

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.expected_conditions import presence_of_element_located
from selenium.webdriver.support.wait import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from news_dashboard.scraper import USER_AGENT

logger = logging.getLogger(__name__)

_ARTICLE_SELECTORS = "article, main, .post-content, .entry-content, p"
_DEFAULT_TIMEOUT = 10.0

# Button text substrings for cookie/consent banners (matched case-insensitively)
_CONSENT_BUTTON_TEXTS = [
    "accept all",
    "allow all",
    "allow cookies",
    "accept cookies",
    "i accept",
    "i agree",
    "agree",
    "consent",
    "got it",
]

# CSS selectors tried in order for modal close buttons
_MODAL_CLOSE_SELECTORS = [
    '[aria-label="Close"]',
    '[aria-label="close"]',
    ".modal-close",
    ".pop-up-close",
    ".popup-close",
    ".modal__close",
    ".close-button",
    ".dialog-close",
    '[data-dismiss="modal"]',
    ".modal .close",
    ".overlay .close",
    "button.close",
]

# JS that removes common overlay/paywall elements and restores body scroll
_OVERLAY_REMOVAL_JS = """
(function() {
    var selectors = [
        '.modal', '.overlay', '.popup', '.pop-up',
        '[role="dialog"]', '[aria-modal="true"]',
        '.cookie-banner', '.cookie-notice', '.cookie-consent',
        '.newsletter-modal', '.subscription-wall',
        '#cookie-banner', '#cookie-notice', '#cookie-consent',
        '#newsletter-modal', '#subscription-wall',
        '.paywall', '#paywall'
    ];
    selectors.forEach(function(sel) {
        document.querySelectorAll(sel).forEach(function(el) { el.remove(); });
    });
    document.body.style.overflow = '';
    document.body.style.position = '';
    document.documentElement.style.overflow = '';
})();
"""

DomainHandler = Callable[[webdriver.Chrome], None]


def _build_options() -> Options:
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument(f"--user-agent={USER_AGENT}")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    prefs: dict[str, int] = {
        "profile.managed_default_content_settings.images": 2,
        "profile.managed_default_content_settings.stylesheet": 2,
        "profile.managed_default_content_settings.media_stream": 2,
    }
    opts.add_experimental_option("prefs", prefs)
    return opts


@contextmanager
def headless_browser() -> Generator[webdriver.Chrome]:
    """Context manager yielding a headless Chrome driver; always calls quit() on exit."""
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=_build_options())
    try:
        yield driver
    finally:
        driver.quit()


def _click_consent_buttons(driver: webdriver.Chrome) -> bool:
    """Find and click cookie/consent banner buttons. Returns True if any were clicked."""
    try:
        buttons = driver.find_elements(By.TAG_NAME, "button")
        for btn in buttons:
            try:
                text = (btn.text or "").strip().lower()
                if any(phrase in text for phrase in _CONSENT_BUTTON_TEXTS):
                    btn.click()
                    logger.info("selenium: clicked consent button %r", btn.text)
                    return True
            except Exception as btn_exc:
                logger.debug("selenium: error interacting with button: %s", btn_exc)
                continue
    except Exception as exc:
        logger.debug("selenium: error scanning consent buttons: %s", exc)
    return False


def _dismiss_modal_close_buttons(driver: webdriver.Chrome) -> bool:
    """Click a modal close button via CSS selectors. Returns True if one was clicked."""
    for selector in _MODAL_CLOSE_SELECTORS:
        try:
            el = driver.find_element(By.CSS_SELECTOR, selector)
            el.click()
            logger.info("selenium: closed modal via selector %r", selector)
            return True
        except NoSuchElementException:
            continue
        except Exception as exc:
            logger.debug("selenium: error clicking modal close %r: %s", selector, exc)
    return False


def _remove_overlays_js(driver: webdriver.Chrome) -> None:
    """Programmatically remove overlay elements and restore body scroll via JS."""
    try:
        driver.execute_script(_OVERLAY_REMOVAL_JS)
        logger.debug("selenium: executed overlay removal JS")
    except Exception as exc:
        logger.debug("selenium: JS overlay removal failed: %s", exc)


def _handle_medium(driver: webdriver.Chrome) -> None:
    """Dismiss Medium metered paywall overlay."""
    try:
        driver.execute_script(
            """
            document.querySelectorAll(
                '.meteredContent, .branch-journeys-top, [data-testid="paywall"]'
            ).forEach(function(el) { el.remove(); });
            var article = document.querySelector('article');
            if (article) { article.style.maxHeight = ''; article.style.overflow = ''; }
            """
        )
        logger.debug("selenium: applied Medium paywall bypass")
    except Exception as exc:
        logger.debug("selenium: Medium handler error: %s", exc)


def _handle_substack(driver: webdriver.Chrome) -> None:
    """Dismiss Substack subscription modals and paywalls."""
    try:
        driver.execute_script(
            """
            document.querySelectorAll(
                '.paywall, .subscription-widget-wrap, .subscribe-widget, [class*="paywall"]'
            ).forEach(function(el) { el.remove(); });
            """
        )
        logger.debug("selenium: applied Substack paywall bypass")
    except Exception as exc:
        logger.debug("selenium: Substack handler error: %s", exc)


# Domain-specific handlers keyed by apex domain
_DOMAIN_HANDLERS: dict[str, DomainHandler] = {
    "medium.com": _handle_medium,
    "substack.com": _handle_substack,
}


def _get_domain_handler(hostname: str) -> DomainHandler | None:
    for domain, handler in _DOMAIN_HANDLERS.items():
        if hostname == domain or hostname.endswith(f".{domain}"):
            return handler
    return None


def dismiss_overlays(driver: webdriver.Chrome, url: str) -> None:
    """Detect and dismiss cookie banners, modal overlays, and soft paywalls.

    Runs four strategies in sequence and logs outcomes for diagnostics:
    1. Click common consent/cookie buttons.
    2. Click modal close buttons via CSS selectors.
    3. Remove remaining overlay elements via JS and restore body scroll.
    4. Run a domain-specific bypass handler (Medium, Substack, …).
    """
    hostname = urllib.parse.urlparse(url).hostname or ""

    consent_clicked = _click_consent_buttons(driver)
    if not consent_clicked:
        logger.debug("selenium: no consent banner found on %s", hostname)

    modal_closed = _dismiss_modal_close_buttons(driver)
    if not modal_closed:
        logger.debug("selenium: no modal close button found on %s", hostname)

    _remove_overlays_js(driver)

    handler = _get_domain_handler(hostname)
    if handler:
        logger.debug("selenium: running domain handler for %s", hostname)
        handler(driver)


def _try_amp_url(url: str) -> str | None:
    """Return an AMP variant of *url* for domains that support it, or None."""
    parsed = urllib.parse.urlparse(url)
    hostname = parsed.hostname or ""
    if "medium.com" in hostname:
        path = parsed.path
        if not path.startswith("/amp"):
            return urllib.parse.urlunparse(parsed._replace(path=f"/amp{path}"))
    return None


def fetch_spa_html(url: str, timeout: float = _DEFAULT_TIMEOUT) -> str:
    """Fetch a JS-rendered page using headless Chrome.

    After the page loads, automatically dismisses cookie banners, modal overlays,
    and soft paywalls before returning the rendered page source.
    """
    amp_url = _try_amp_url(url)
    if amp_url:
        try:
            result = _fetch_with_cleanup(amp_url, timeout=timeout)
            if result:
                logger.info("selenium: AMP fetch succeeded for %r", url)
                return result
        except Exception as exc:
            logger.debug("selenium: AMP fetch failed for %r: %s", url, exc)

    return _fetch_with_cleanup(url, timeout=timeout)


def _fetch_with_cleanup(url: str, timeout: float = _DEFAULT_TIMEOUT) -> str:
    """Fetch *url* with headless Chrome, run overlay dismissal, return page source."""
    with headless_browser() as driver:
        driver.set_page_load_timeout(timeout)
        driver.set_script_timeout(timeout)
        navigation_timed_out = False
        try:
            driver.get(url)
        except TimeoutException:
            navigation_timed_out = True
            logger.debug("selenium: page load timeout for %r — using partial page source", url)
            try:
                driver.execute_script("window.stop()")
            except Exception as exc:
                logger.debug("selenium: failed to stop loading after timeout for %r: %s", url, exc)

        if not navigation_timed_out:
            try:
                WebDriverWait(driver, timeout).until(
                    presence_of_element_located((By.CSS_SELECTOR, _ARTICLE_SELECTORS))
                )
            except TimeoutException:
                logger.debug(
                    "selenium: article selector timeout for %r — using raw page source", url
                )

        dismiss_overlays(driver, url)
        return str(driver.page_source)
