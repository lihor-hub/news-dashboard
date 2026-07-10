"""Business logic for watchlist CRUD, previews, and nudges."""

from __future__ import annotations

from news_dashboard.watchlist_agent import (
    WatchlistNotFoundError,
    create_watchlist,
    delete_watchlist,
    list_nudges,
    list_watchlists,
    preview_matches,
    update_watchlist,
)

__all__ = [
    "WatchlistNotFoundError",
    "create_watchlist",
    "delete_watchlist",
    "list_nudges",
    "list_watchlists",
    "preview_matches",
    "update_watchlist",
]
