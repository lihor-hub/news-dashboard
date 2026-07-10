"""Business logic for tags and article-tag relationships."""

from __future__ import annotations

from news_dashboard.body_fetch import get_article
from news_dashboard.ingest.service import list_articles
from news_dashboard.tags import (
    add_tag_to_article,
    create_tag,
    delete_tag,
    list_tags,
    list_tags_for_article,
    remove_tag_from_article,
    rename_tag,
)

__all__ = [
    "add_tag_to_article",
    "create_tag",
    "delete_tag",
    "get_article",
    "list_articles",
    "list_tags",
    "list_tags_for_article",
    "remove_tag_from_article",
    "rename_tag",
]
