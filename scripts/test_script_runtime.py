"""Exercise script entry points without network or database access."""

import io
import json
import runpy
import sys
from pathlib import Path
from unittest.mock import MagicMock
from urllib.request import Request

import ensure_demo_database
import psycopg
import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_demo_database_quotes_identifier(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = MagicMock()
    connection.execute.return_value.fetchone.return_value = None
    connect = MagicMock()
    connect.return_value.__enter__.return_value = connection
    monkeypatch.setattr(psycopg, "connect", connect)
    monkeypatch.setenv("DEMO_DATABASE_URL", 'postgresql://localhost/demo"db')
    ensure_demo_database.main()
    statement = connection.execute.call_args.args[0]
    assert statement.as_string() == 'CREATE DATABASE "demo""db"'  # noqa: S101
    connect.assert_called_once_with("postgresql://localhost/postgres", autocommit=True)


def test_verification_cli_uses_default_integer_attempts(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    revision = "a" * 40

    def response(request: Request, timeout: int) -> io.BytesIO:
        assert timeout == 15  # noqa: S101
        assert request.full_url.endswith(f"?revision={revision}")  # noqa: S101
        return io.BytesIO(json.dumps({"revision": revision, "version": "1.2.3"}).encode())

    monkeypatch.setattr("urllib.request.urlopen", response)
    monkeypatch.setattr(
        sys, "argv", ["verify-deployed-build.py", "https://news.example", revision, "1.2.3"]
    )
    runpy.run_path(str(ROOT / "scripts/verify-deployed-build.py"), run_name="__main__")
    assert f"Verified public build {revision}" in capsys.readouterr().out  # noqa: S101
