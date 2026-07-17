"""Tests for the Selenium overlay/paywall bypass client (issue #354).

Skipped automatically when the `selenium` package is not installed.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

pytest = __import__("pytest")
pytest.importorskip("selenium")

from unittest.mock import MagicMock, call, patch  # noqa: E402

from selenium.common.exceptions import (  # noqa: E402
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)

from news_dashboard.selenium_client import (  # noqa: E402
    _click_consent_buttons,
    _dismiss_modal_close_buttons,
    _fetch_with_cleanup,
    _get_domain_handler,
    _install_request_safety,
    _meaningful_content_present,
    _remove_overlays_js,
    _try_amp_url,
    dismiss_overlays,
    fetch_spa_html,
)
from news_dashboard.url_safety import UnsafeUrlError  # noqa: E402


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


def test_try_amp_url_medium_subdomain() -> None:
    amp = _try_amp_url("https://blog.medium.com/post")
    assert amp is not None
    assert "/amp/" in amp


def test_try_amp_url_medium_lookalike_suffix_returns_none() -> None:
    assert _try_amp_url("https://medium.com.evil.example/post") is None


def test_try_amp_url_medium_lookalike_prefix_returns_none() -> None:
    assert _try_amp_url("https://notmedium.com/post") is None


# ── Fetch timeout handling ───────────────────────────────────────────────────


def test_fetch_with_cleanup_configures_navigation_timeouts() -> None:
    driver = MagicMock()
    driver.page_source = "<html><article>loaded</article></html>"
    browser_context = MagicMock()
    browser_context.__enter__.return_value = driver

    with (
        patch("news_dashboard.selenium_client.headless_browser", return_value=browser_context),
        patch("news_dashboard.selenium_client.WebDriverWait") as wait_cls,
        patch("news_dashboard.selenium_client.dismiss_overlays") as dismiss_mock,
    ):
        result = _fetch_with_cleanup("https://example.com/article", timeout=3.5)

    assert result == "<html><article>loaded</article></html>"
    assert driver.mock_calls[1:4] == [
        call.set_page_load_timeout(3.5),
        call.set_script_timeout(3.5),
        call.get("https://example.com/article"),
    ]
    wait_cls.assert_called_once_with(driver, 3.5)
    dismiss_mock.assert_called_once_with(driver, "https://example.com/article")


def test_meaningful_content_present_rejects_title_only_dom() -> None:
    driver = MagicMock()
    element = MagicMock()
    element.text = "The Python Tutorial — Python documentation"
    driver.find_elements.return_value = [element]

    assert _meaningful_content_present(driver) is False


def test_meaningful_content_present_accepts_substantial_dom() -> None:
    driver = MagicMock()
    paragraph = (
        "This rendered paragraph explains a technical topic with detailed examples, "
        "limitations, tradeoffs, and practical consequences for an interested reader who "
        "needs enough trustworthy source material to generate a grounded learning lesson."
    )
    first = MagicMock()
    first.text = paragraph
    second = MagicMock()
    second.text = paragraph
    driver.find_elements.return_value = [first, second]

    assert _meaningful_content_present(driver) is True


def test_fetch_with_cleanup_stops_loading_after_navigation_timeout() -> None:
    driver = MagicMock()
    driver.get.side_effect = TimeoutException("page load timed out")
    driver.page_source = "<html><p>partial text</p></html>"
    browser_context = MagicMock()
    browser_context.__enter__.return_value = driver

    with (
        patch("news_dashboard.selenium_client.headless_browser", return_value=browser_context),
        patch("news_dashboard.selenium_client.WebDriverWait") as wait_cls,
        patch("news_dashboard.selenium_client.dismiss_overlays") as dismiss_mock,
    ):
        result = _fetch_with_cleanup("https://example.com/slow", timeout=1.0)

    assert result == "<html><p>partial text</p></html>"
    driver.execute_script.assert_called_with("window.stop()")
    wait_cls.return_value.until.assert_not_called()
    dismiss_mock.assert_called_once_with(driver, "https://example.com/slow")


def test_request_safety_fails_unsafe_browser_request() -> None:
    driver = MagicMock()
    blocked = _install_request_safety(driver)
    callback = driver.network.add_request_handler.call_args.args[1]
    request = MagicMock(url="http://127.0.0.1/private")

    callback(request)

    assert blocked == ["http://127.0.0.1/private"]
    request.fail.assert_called_once()


def test_request_safety_records_interception_capability_failure() -> None:
    driver = MagicMock()
    blocked = _install_request_safety(driver)
    callback = driver.network.add_request_handler.call_args.args[1]
    request = MagicMock(url="https://example.com/article")
    request.continue_request.side_effect = WebDriverException("unsupported")

    with patch("news_dashboard.selenium_client.validate_server_fetch_url"):
        callback(request)

    assert blocked == ["interception-error:https://example.com/article"]


def test_fetch_with_cleanup_rejects_unsafe_request_even_after_timeout() -> None:
    driver = MagicMock()
    driver.get.side_effect = TimeoutException("page load timed out")
    driver.current_url = "https://example.com/slow"
    browser_context = MagicMock()
    browser_context.__enter__.return_value = driver

    with (
        patch("news_dashboard.selenium_client.headless_browser", return_value=browser_context),
        patch(
            "news_dashboard.selenium_client._install_request_safety",
            return_value=["http://169.254.169.254/latest/meta-data"],
        ),
        pytest.raises(UnsafeUrlError),
    ):
        _fetch_with_cleanup("https://example.com/slow", timeout=1.0)


def test_fetch_spa_html_renders_local_javascript_fixture() -> None:
    paragraph = (
        "This JavaScript-rendered article explains a technical topic with detailed "
        "examples, limitations, tradeoffs, and practical consequences for readers."
    )

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = (
                "<html><body><main id='content'></main><script>"
                "document.getElementById('content').innerHTML = "
                f"`<p>{paragraph}</p><p>{paragraph}</p>`;"
                "</script></body></html>"
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002, ARG002
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/"
    html = ""
    try:
        with patch("news_dashboard.selenium_client.validate_server_fetch_url"):
            try:
                html = fetch_spa_html(url, timeout=5.0)
            except WebDriverException as exc:
                pytest.skip(f"Chrome is unavailable: {exc}")
        if paragraph not in html:
            pytest.skip("Installed Chrome does not support Selenium BiDi interception")
        assert paragraph in html
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
