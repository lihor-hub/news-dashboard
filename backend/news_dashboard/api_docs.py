"""Toggle for the FastAPI interactive API docs (Swagger UI, ReDoc, OpenAPI schema).

Gated by the ``ENABLE_API_DOCS`` env var (off by default) so a public
deployment doesn't leak its full API surface to anonymous visitors. Set
``ENABLE_API_DOCS=true`` (e.g. in local dev) to serve ``/docs``, ``/redoc``,
and ``/openapi.json`` as usual.
"""

from __future__ import annotations

import os

DOCS_PATHS = frozenset({"/docs", "/redoc", "/openapi.json"})
INTERACTIVE_DOCS_PATHS = frozenset({"/docs", "/redoc"})


def api_docs_enabled() -> bool:
    return os.getenv("ENABLE_API_DOCS", "").strip().lower() in ("1", "true", "yes", "on")
