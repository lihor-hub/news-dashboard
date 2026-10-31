"""Opt-in real-password PostgreSQL built-SPA recap acceptance, no API/auth mocks."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import uvicorn

from news_dashboard.auth import create_user
from news_dashboard.db import connect
from news_dashboard.main import SPAStaticFiles, app
from news_dashboard.recaps.service import assemble_weekly_recap, get_recap, save_weekly_recap

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_PROGRESS_BROWSER") != "1", reason="Opt-in real recap browser"
    ),
]


def test_recap_browser(pg_clean: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    monkeypatch.setenv("KEYCLOAK_AUTH_ENABLED", "false")
    app.dependency_overrides.clear()
    user = create_user("live-recap-test", "test-password-not-production")
    uid = user["id"]
    with connect() as conn:
        conn.execute(
            """UPDATE users SET progress_timezone='America/New_York',daily_welcome_enabled=FALSE
               WHERE id=%s""",
            (uid,),
        )
        conn.execute(
            """INSERT INTO user_daily_visits(user_id,local_date,timezone,first_visited_at)
            VALUES (%s,'2026-01-05','America/New_York','2026-01-05T12:00:00Z')""",
            (uid,),
        )
        conn.execute(
            """INSERT INTO user_activity_totals(user_id,total_ms,measured_since)
            VALUES (%s,59000,'2026-01-05T12:00:00Z')""",
            (uid,),
        )
        conn.execute(
            """INSERT INTO user_activity_days(user_id,local_date,timezone,active_ms)
            VALUES (%s,'2026-01-05','America/New_York',59000)""",
            (uid,),
        )
        for key in ("daily_streak_3", "articles_read_1", "topic_python_1", "active_time_900"):
            conn.execute(
                """INSERT INTO user_achievements(user_id,achievement_key,origin,earned_at)
                VALUES (%s,%s,'live','2026-01-05T12:00:00Z')""",
                (uid, key),
            )
    scheduled = datetime(2026, 1, 12, 9, tzinfo=timezone.utc)
    oldest = None
    for week in range(15):
        data = assemble_weekly_recap(uid, now=scheduled + timedelta(weeks=week))
        saved = save_weekly_recap(uid, data, None)["snapshot"]
        if week == 0:
            oldest = saved
    assert oldest is not None
    root = Path(__file__).resolve().parents[2]
    dist = root / "frontend" / "dist"
    assert (dist / "index.html").exists(), "Build SPA first"
    if not any(getattr(route, "name", None) == "static" for route in app.routes):
        app.mount("/", SPAStaticFiles(directory=dist, html=True), name="static")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
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
        result = subprocess.run(  # noqa: S603 - fixed repository test script
            [node, "e2e/recap-progress-live.mjs"],
            cwd=root,
            env={
                **os.environ,
                "LIVE_PROGRESS_URL": f"http://127.0.0.1:{port}",
                "RECAP_ID": str(oldest["id"]),
            },
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if storage := os.getenv("BB_THREAD_STORAGE"):
            (Path(storage) / "recap-browser-node.log").write_text(result.stdout + result.stderr)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "RECAP_PROGRESS_LIVE_OK" in result.stdout
        assert get_recap(uid, oldest["id"]) == oldest
    finally:
        server.should_exit = True
        thread.join(timeout=10)
