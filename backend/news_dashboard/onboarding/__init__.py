"""New-user onboarding: interest selection and source recommendations.

Feature-module package: HTTP routes live in :mod:`~news_dashboard.onboarding.router`,
business logic in :mod:`~news_dashboard.onboarding.service`, and request models in
:mod:`~news_dashboard.onboarding.models`. See ``docs/adr`` for the layout rationale.

The router is imported directly from the ``router`` submodule (``from
news_dashboard.onboarding.router import router``) rather than re-exported here, so
the submodule name is never shadowed.
"""

from __future__ import annotations
