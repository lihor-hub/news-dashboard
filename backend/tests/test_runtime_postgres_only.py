"""Guard that runtime database code stays PostgreSQL-specific (issue #227).

The recommendation epic must not regress the project's PostgreSQL-only runtime
contract: no SQLite fallback, no database sniffing, no placeholder translation,
and no generic multi-database SQL creeping into the serving path.  These tests
scan the runtime source statically so the contract holds even for code paths
that are awkward to exercise at runtime.

The one-off ``migrate.py`` CLI is intentionally excluded: it reads a legacy
SQLite file to import it *into* Postgres, which is a migration tool, not a
runtime fallback.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import news_dashboard

PACKAGE_ROOT = Path(news_dashboard.__file__).parent

# ``migrate.py`` legitimately reads SQLite to import legacy data into Postgres.
_EXCLUDED = {"migrate.py"}


def _runtime_modules() -> list[Path]:
    return sorted(path for path in PACKAGE_ROOT.glob("*.py") if path.name not in _EXCLUDED)


def test_runtime_modules_exist() -> None:
    # Sanity check so an empty glob cannot vacuously pass the guards below.
    names = {path.name for path in _runtime_modules()}
    assert {"db.py", "ingest.py", "recommendations.py", "recommendation_jobs.py"} <= names


@pytest.mark.parametrize("module", _runtime_modules(), ids=lambda p: p.name)
def test_runtime_module_does_not_use_sqlite(module: Path) -> None:
    # Detect actual SQLite *usage* (import/connect), not docstrings that merely
    # reaffirm the "no SQLite fallback" contract.
    source = module.read_text(encoding="utf-8").lower()
    assert "import sqlite3" not in source, f"{module.name} imports sqlite3"
    assert "sqlite3." not in source, f"{module.name} uses the sqlite3 module"
    assert "sqlite://" not in source, f"{module.name} builds a sqlite DSN"


@pytest.mark.parametrize("module", _runtime_modules(), ids=lambda p: p.name)
def test_runtime_module_has_no_qmark_placeholder_translation(module: Path) -> None:
    """No code rewrites psycopg ``%s`` placeholders into SQLite ``?`` style."""
    source = module.read_text(encoding="utf-8")
    assert '"?"' not in source
    assert "'?'" not in source
    assert '.replace("%s"' not in source
    assert "paramstyle" not in source


@pytest.mark.parametrize("module", _runtime_modules(), ids=lambda p: p.name)
def test_runtime_module_has_no_sqlite_only_sql(module: Path) -> None:
    """No SQLite-flavoured statements that imply a non-Postgres backend."""
    source = module.read_text(encoding="utf-8").upper()
    assert "INSERT OR IGNORE" not in source
    assert "INSERT OR REPLACE" not in source
    assert "PRAGMA " not in source
    assert "AUTOINCREMENT" not in source


def test_non_postgres_database_url_is_rejected() -> None:
    """The runtime refuses any non-Postgres DSN rather than sniffing/falling back."""
    from news_dashboard.db import active_database_url

    with pytest.raises(RuntimeError, match="DATABASE_URL must start"):
        active_database_url("sqlite:///tmp/news.db")
