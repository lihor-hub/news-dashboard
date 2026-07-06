"""Public system/health endpoints: health, liveness, readiness, metrics, config, version, changelog.

Feature-module package: HTTP routes live in :mod:`~news_dashboard.system.router`,
business logic in :mod:`~news_dashboard.system.service`. See ``docs/adr`` for the
layout rationale.

The router is imported directly from the ``router`` submodule (``from
news_dashboard.system.router import router``) rather than re-exported here, so
the submodule name is never shadowed.
"""

from __future__ import annotations
