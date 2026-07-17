#!/usr/bin/env python3
"""Run the public-content extractor against an opt-in live URL corpus."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from news_dashboard.body_fetch import extract_public_content

DEFAULT_URLS = (
    "https://capnproto.org/",
    "https://react.dev/learn/thinking-in-react",
    "https://developer.mozilla.org/en-US/docs/Web/API/Document_Object_Model",
    "https://github.blog/ai-and-ml/generative-ai/"
    "what-is-retrieval-augmented-generation-and-what-does-it-do-for-generative-ai/",
    "https://blog.cloudflare.com/ai-platform/",
    "https://quotes.toscrape.com/js/",
)


def run(urls: Sequence[str]) -> int:
    """Extract every URL and print bounded diagnostic fields."""
    for url in urls:
        result = extract_public_content(url, allow_ai=False)
        quality = result.quality
        latency_ms = sum(attempt.latency_ms for attempt in result.attempts)
        print(  # noqa: T201 - this is an explicit command-line diagnostic
            " ".join(
                (
                    f"status={result.status}",
                    f"method={result.method or '-'}",
                    f"chars={quality.character_count if quality else 0}",
                    f"accepted={str(bool(quality and quality.accepted)).lower()}",
                    f"latency_ms={latency_ms}",
                    f"failure={result.failure_reason or '-'}",
                    f"url={url}",
                )
            )
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("urls", nargs="*", help="Public HTTP(S) URLs; defaults to the smoke corpus")
    args = parser.parse_args(argv)
    urls = tuple(args.urls) or DEFAULT_URLS
    return run(urls)


if __name__ == "__main__":
    raise SystemExit(main())
