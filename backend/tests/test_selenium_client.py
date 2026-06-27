"""Tests for the Selenium overlay/paywall bypass client (issue #354).

Skipped automatically when the `selenium` package is not installed.
"""

from __future__ import annotations

pytest = __import__("pytest")
pytest.importorskip("selenium")

from unittest.mock import MagicMock, patch  # noqa: E402

from selenium.common.exceptions import NoSuchElementException  # noqa: E402

from news_dashboard.selenium_client import (  # noqa: E402
    _click_consent_buttons,
    _dismiss_modal_close_buttons,
    _get_domain_handler,
    _remove_overlays_js,
    _try_amp_url,
    dismiss_overlays,
)


def _make_driver(*, buttons: list[str] | None = None) -> MagicMock:
    """Return a mock webdriver with configurable button elements."""
    driver = MagicMock()
    mock_buttons: list[MagicMock] = []
    for text in buttons or []:
        btn = MagicMock()
        btn.text = text
        mock_buttons.append(btn)
    driver.find_elements.return_value = mock_buttons
    return driver


# ── Cookie / consent banner ───────────────────────────────────────────────────


def test_click_consent_buttons_accepts_all() -> None:
    driver = _make_driver(buttons=["Reject", "Accept All"])
    result = _click_consent_buttons(driver)
    assert result is True
    clicked_btn = driver.find_elements.return_value[1]
    clicked_btn.click.assert_called_once()


def test_click_consent_buttons_no_match_returns_false() -> None:
    driver = _make_driver(buttons=["Subscribe", "Log in"])
    result = _click_consent_buttons(driver)
    assert result is False


def test_click_consent_buttons_empty_page_returns_false() -> None:
    driver = _make_driver(buttons=[])
    result = _click_consent_buttons(driver)
    assert result is False


def test_click_consent_buttons_case_insensitive() -> None:
    driver = _make_driver(buttons=["ALLOW COOKIES"])
    result = _click_consent_buttons(driver)
    assert result is True


# ── Modal close buttons ───────────────────────────────────────────────────────


def test_dismiss_modal_close_buttons_clicks_first_match() -> None:
    driver = MagicMock()
    close_el = MagicMock()
    driver.find_element.return_value = close_el
    result = _dismiss_modal_close_buttons(driver)
    assert result is True
    close_el.click.assert_called_once()


def test_dismiss_modal_close_buttons_no_element_returns_false() -> None:
    driver = MagicMock()
    driver.find_element.side_effect = NoSuchElementException
    result = _dismiss_modal_close_buttons(driver)
    assert result is False


# ── JS overlay removal ────────────────────────────────────────────────────────


def test_remove_overlays_js_executes_script() -> None:
    driver = MagicMock()
    _remove_overlays_js(driver)
    driver.execute_script.assert_called_once()
    script = driver.execute_script.call_args[0][0]
    assert "cookie-banner" in script
    assert "overflow" in script


def test_remove_overlays_js_silences_errors() -> None:
    driver = MagicMock()
    driver.execute_script.side_effect = Exception("JS error")
    _remove_overlays_js(driver)  # must not raise


# ── dismiss_overlays pipeline ─────────────────────────────────────────────────


def test_dismiss_overlays_calls_js_cleanup() -> None:
    driver = _make_driver(buttons=["Accept All"])
    with patch("news_dashboard.selenium_client._remove_overlays_js") as mock_js:
        dismiss_overlays(driver, "https://example.com/article")
    mock_js.assert_called_once_with(driver)


def test_dismiss_overlays_medium_handler_runs() -> None:
    driver = _make_driver()
    mock_handler = MagicMock()
    with patch("news_dashboard.selenium_client._DOMAIN_HANDLERS", {"medium.com": mock_handler}):
        dismiss_overlays(driver, "https://medium.com/some-post")
    mock_handler.assert_called_once_with(driver)


def test_dismiss_overlays_substack_handler_runs() -> None:
    driver = _make_driver()
    mock_handler = MagicMock()
    with patch("news_dashboard.selenium_client._DOMAIN_HANDLERS", {"substack.com": mock_handler}):
        dismiss_overlays(driver, "https://newsletter.substack.com/p/article")
    mock_handler.assert_called_once_with(driver)


def test_dismiss_overlays_no_handler_for_unknown_domain() -> None:
    driver = _make_driver()
    mock_handler = MagicMock()
    with patch("news_dashboard.selenium_client._DOMAIN_HANDLERS", {"medium.com": mock_handler}):
        dismiss_overlays(driver, "https://example.com/article")
    mock_handler.assert_not_called()


# ── Domain handler registry ───────────────────────────────────────────────────


def test_get_domain_handler_medium() -> None:
    assert _get_domain_handler("medium.com") is not None


def test_get_domain_handler_medium_subdomain() -> None:
    assert _get_domain_handler("towardsdatascience.medium.com") is not None


def test_get_domain_handler_substack() -> None:
    assert _get_domain_handler("newsletter.substack.com") is not None


def test_get_domain_handler_unknown_returns_none() -> None:
    assert _get_domain_handler("example.com") is None


# ── AMP URL construction ──────────────────────────────────────────────────────


def test_try_amp_url_medium() -> None:
    amp = _try_amp_url("https://medium.com/@user/some-post-abc123")
    assert amp is not None
    assert "/amp/" in amp


def test_try_amp_url_medium_already_amp() -> None:
    assert _try_amp_url("https://medium.com/amp/@user/some-post") is None


def test_try_amp_url_non_medium_returns_none() -> None:
    assert _try_amp_url("https://example.com/article") is None
