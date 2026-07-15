#!/usr/bin/env python3
"""Synchronize the canonical local prompt catalog to Langfuse production."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from news_dashboard.prompt_catalog import PROMPT_CATALOG, PromptCatalogEntry  # noqa: E402

_ENVIRONMENT_VARIABLES = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST")


def _sdk_prompt(entry: PromptCatalogEntry) -> str | list[dict[str, str]]:
    return entry.fallback()


def _matches(current: Any, entry: PromptCatalogEntry) -> bool:
    return getattr(current, "type", entry.type) == entry.type and getattr(
        current, "prompt", None
    ) == _sdk_prompt(entry)


def _sync(client: Any) -> None:
    for entry in PROMPT_CATALOG:
        try:
            current = client.get_prompt(entry.name, label="production", type=entry.type)
        except Exception:  # Langfuse uses multiple exception types for an absent prompt.
            current = None

        if current is not None and _matches(current, entry):
            print(f"unchanged {entry.name} v{getattr(current, 'version', 'unknown')}")
            continue

        create_kwargs: dict[str, Any] = {
            "name": entry.name,
            "type": entry.type,
            "prompt": _sdk_prompt(entry),
            "labels": ["production"],
        }
        if entry.commit_message is not None:
            create_kwargs["commit_message"] = entry.commit_message
        created = client.create_prompt(**create_kwargs)
        print(f"synced {entry.name} v{getattr(created, 'version', 'unknown')}")


def main() -> int:
    missing = [name for name in _ENVIRONMENT_VARIABLES if not os.getenv(name)]
    if missing:
        print(f"missing required environment variables: {', '.join(missing)}", file=sys.stderr)
        return 2

    from langfuse import Langfuse

    client = Langfuse(
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        secret_key=os.environ["LANGFUSE_SECRET_KEY"],
        host=os.environ["LANGFUSE_HOST"],
    )
    _sync(client)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
