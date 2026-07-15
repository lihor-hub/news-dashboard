from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI


def test_lifespan_opens_and_closes_connection_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    """FastAPI startup owns the runtime pool for the process lifetime."""
    from news_dashboard import main

    calls: list[str] = []

    monkeypatch.setattr(main, "init_error_tracking", lambda: calls.append("error_tracking"))
    monkeypatch.setattr(main, "open_connection_pool", lambda: calls.append("pool_open"))
    monkeypatch.setattr(main, "init_auth", lambda: calls.append("auth"))
    monkeypatch.setattr(main, "sync_sources", lambda: calls.append("sources"))
    monkeypatch.setattr(main, "start_scheduler", lambda: calls.append("scheduler_start"))
    monkeypatch.setattr(main, "stop_scheduler", lambda: calls.append("scheduler_stop"))
    monkeypatch.setattr(main, "close_connection_pool", lambda: calls.append("pool_close"))
    monkeypatch.delenv("DEMO_MODE", raising=False)

    async def run_lifespan() -> None:
        async with main.lifespan(FastAPI()):
            calls.append("running")

    asyncio.run(run_lifespan())

    assert calls == [
        "error_tracking",
        "pool_open",
        "auth",
        "sources",
        "scheduler_start",
        "running",
        "scheduler_stop",
        "pool_close",
    ]
