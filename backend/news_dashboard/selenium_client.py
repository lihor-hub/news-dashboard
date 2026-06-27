"""Headless Chrome browser client for JS-rendered (SPA) web pages."""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
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


def fetch_spa_html(url: str, timeout: float = _DEFAULT_TIMEOUT) -> str:
    """Fetch a JS-rendered page using headless Chrome.

    Waits up to *timeout* seconds for common article selectors to appear in the
    DOM before returning the rendered page source.
    """
    with headless_browser() as driver:
        driver.get(url)
        try:
            WebDriverWait(driver, timeout).until(
                presence_of_element_located((By.CSS_SELECTOR, _ARTICLE_SELECTORS))
            )
        except TimeoutException:
            logger.debug("selenium: article selector timeout for %r — using raw page source", url)
        return str(driver.page_source)
