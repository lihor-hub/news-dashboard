"""Reading Goals and AI-generated retention quizzes.

Feature-module package: HTTP routes live in :mod:`~news_dashboard.quizzes.router`,
business logic in :mod:`~news_dashboard.quizzes.service`, and request models in
:mod:`~news_dashboard.quizzes.models`. See ``docs/adr`` for the layout rationale.

The router is imported directly from the ``router`` submodule (``from
news_dashboard.quizzes.router import router``) rather than re-exported here, so
the submodule name is never shadowed.
"""

from __future__ import annotations
