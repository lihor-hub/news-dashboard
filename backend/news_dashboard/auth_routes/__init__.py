"""HTTP routes for login, registration, OTP, Keycloak SSO, and the current user.

Feature-module package: HTTP routes live in
:mod:`~news_dashboard.auth_routes.router`, request models in
:mod:`~news_dashboard.auth_routes.models`. Business logic (session tokens,
Keycloak exchange, user/OTP persistence) stays in the existing
:mod:`~news_dashboard.auth` module, which is imported across ~60 files
(``require_auth``, ``require_admin``, etc.); this package is a thin HTTP
layer on top of it rather than a replacement. See ``docs/adr`` for the
feature-module layout rationale.

The routers are imported directly from the ``router`` submodule (``from
news_dashboard.auth_routes.router import public_router, router``) rather than
re-exported here, so the submodule name is never shadowed.
"""

from __future__ import annotations
