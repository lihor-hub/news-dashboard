"""Recommendation admin/health endpoints (``/api/recommendations/*``).

Feature-module package: HTTP routes live in
:mod:`~news_dashboard.recommendations_routes.router`. Business logic already
lived in the flat sibling modules :mod:`~news_dashboard.recommendation_jobs`
and :mod:`~news_dashboard.recommendations` before this package existed, so the
router delegates to them directly rather than duplicating a ``service``
module. The package is named ``recommendations_routes`` (not
``recommendations``) to avoid shadowing the existing
:mod:`~news_dashboard.recommendations` module.

The router is imported directly from the ``router`` submodule (``from
news_dashboard.recommendations_routes.router import router``) rather than
re-exported here, so the submodule name is never shadowed.
"""

from __future__ import annotations
