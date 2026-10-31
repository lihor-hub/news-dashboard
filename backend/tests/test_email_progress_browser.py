"""Opt-in built SPA, PostgreSQL and real cookie/password/OTP email acceptance.

Only SMTP and the external SSO provider exchange are fixtures; app auth is real.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pytest
import uvicorn
from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from news_dashboard.auth import create_user
from news_dashboard.briefing_email.progress import select_progress
from news_dashboard.briefing_email.rendering import render_briefing_email
from news_dashboard.db import connect
from news_dashboard.main import SPAStaticFiles, app
from news_dashboard.reading_progress.daily import lock_account
from news_dashboard.reading_progress.rewards import award_rewards

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_PROGRESS_BROWSER") != "1", reason="Opt-in real-backed mail acceptance"
    ),
]


def test_email_destination_real_auth_browser(
    pg_clean: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("KEYCLOAK_AUTH_ENABLED", "false")
    app.dependency_overrides.clear()
    user = create_user("live-email-test", "test-password-not-production")
    viewer = create_user("live-email-viewer", "test-password-not-production")
    now = datetime(2026, 1, 15, 12, tzinfo=timezone.utc)
    with connect() as conn:
        conn.execute("UPDATE users SET daily_welcome_enabled=false WHERE id=%s", (viewer["id"],))
        conn.execute(
            """UPDATE users SET email='live-email@example.test',daily_welcome_enabled=false
               WHERE id=%s""",
            (user["id"],),
        )
        lock_account(conn, user["id"])
        award_rewards(
            conn,
            user["id"],
            cause_key="mail-fixture",
            origin="live",
            earned_at=now - timedelta(hours=1),
            candidates=[
                {"key": "topic_python_1", "criteria_version": 1, "progress": 1, "target": 1}
            ],
        )
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    payload = select_progress(
        user["id"], recipient="live-email@example.test", base_url=base, now=now
    )
    assert payload
    rendered = render_briefing_email(
        {
            "title": "Daily",
            "summary": "News summary",
            "content": {"sections": [{"title": "News", "body": "A news story."}]},
        },
        progress=payload,
        local_date=now.date(),
        timezone_name="UTC",
        briefing_url=base + "/briefs/1",
        preferences_url=base + "/settings",
        unsubscribe_url=base + "/email/briefing/unsubscribe?token=fixture",
    )
    codes: list[str] = []
    monkeypatch.setattr(
        "news_dashboard.email.send_otp_email", lambda _email, code: codes.append(code)
    )

    async def exchange(_code: str) -> dict[str, Any]:
        return user

    monkeypatch.setattr("news_dashboard.auth_routes.router.exchange_keycloak_code", exchange)
    # Keep the provider fixture outside the PWA's app-navigation fallback.
    monkeypatch.setattr(
        "news_dashboard.auth_routes.router.keycloak_authorization_url",
        lambda state: base + "/auth/__email_provider?" + urlencode({"state": state}),
    )

    def mail_fixture() -> HTMLResponse:
        return HTMLResponse(rendered.html_body)

    def provider_fixture(request: Request) -> RedirectResponse:
        return RedirectResponse(
            base
            + "/auth/callback?"
            + urlencode(
                {"state": request.query_params["state"], "code": "external-provider-fixture"}
            )
        )

    root = Path(__file__).resolve().parents[2]
    dist = root / "frontend" / "dist"
    assert (dist / "index.html").exists(), "Build SPA first"
    # Insert fixtures before a preexisting static mount from another serial browser test.
    static = [route for route in app.routes if getattr(route, "name", None) == "static"]
    for route in static:
        app.routes.remove(route)
    app.add_api_route("/__email_fixture", mail_fixture)
    app.add_api_route("/auth/__email_provider", provider_fixture)
    app.mount("/", SPAStaticFiles(directory=dist, html=True), name="static")
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            lifespan="off",
            log_level="warning",
            loop="asyncio",
            http="h11",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert thread.is_alive()
        assert time.monotonic() < deadline
        time.sleep(0.05)
    try:
        node = shutil.which("node")
        assert node
        with subprocess.Popen(  # noqa: S603 - fixed repository browser script
            [node, "e2e/email-progress-live.mjs"],
            cwd=root,
            env={**os.environ, "LIVE_PROGRESS_URL": base},
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        ) as proc:
            assert proc.stdout
            assert proc.stdin
            output = []
            watchdog = threading.Timer(120, proc.kill)
            watchdog.start()
            try:
                for line in proc.stdout:
                    output.append(line)
                    event = line.strip()
                    if event == "MAIL_OPENED":
                        with connect() as conn:
                            for table in (
                                "user_daily_visits",
                                "user_activity_days",
                                "user_read_credits",
                            ):
                                assert (
                                    conn.execute(
                                        f"SELECT count(*) AS n FROM {table} WHERE user_id=%s",
                                        (user["id"],),
                                    ).fetchone()["n"]
                                    == 0
                                )
                        proc.stdin.write("CONTINUE\n")
                        proc.stdin.flush()
                    elif event == "OTP_CODE":
                        assert codes
                        proc.stdin.write(codes[-1] + "\n")
                        proc.stdin.flush()
                    elif event == "ENABLE_SSO":
                        monkeypatch.setenv("KEYCLOAK_AUTH_ENABLED", "true")
                        monkeypatch.setenv("KEYCLOAK_SERVER_URL", "https://provider.invalid")
                        monkeypatch.setenv("APP_BASE_URL", base)
                        proc.stdin.write("CONTINUE\n")
                        proc.stdin.flush()
                assert proc.wait(timeout=10) == 0, "".join(output)
                assert "EMAIL_PROGRESS_LIVE_OK" in "".join(output)
                if storage := os.getenv("BB_THREAD_STORAGE"):
                    (Path(storage) / "email-browser-stdout.log").write_text("".join(output))
            finally:
                watchdog.cancel()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        app.routes[:] = [
            route
            for route in app.routes
            if getattr(route, "path", "") not in {"/__email_fixture", "/auth/__email_provider"}
        ]
