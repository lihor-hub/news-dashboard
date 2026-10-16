#!/usr/bin/env python3
"""Run the real optional browser against in-memory HTML, without live websites."""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import platform
import sys
from importlib.metadata import version
from typing import Any

# LiteLLM otherwise checks a remote price map at import time.
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"

HTML = """<!doctype html><html><body><article>
<h1 id="title">Unrendered title</h1>
<p>Știri from our deterministic local article explain how public libraries lend
books, preserve archives, and help residents learn practical skills. Visitors
can read complete reports about neighborhood services without signing into an
account or opening a connection to any outside website.</p>
<p>The second paragraph describes a community garden where volunteers grow
vegetables, share tools, and teach children about the seasons. Every sentence
belongs to this offline fixture, so the browser extraction result stays stable
when the network is unavailable.</p>
<p>Readers can compare these public services and plan their next visit. The
complete story contains enough substantive text to satisfy the existing
application quality rules even when Markdown combines adjacent paragraphs.</p>
<script>document.getElementById('title').textContent = 'Browser rendered Știri';</script>
</article></body></html>"""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


async def _browser_smoke() -> dict[str, Any]:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

    from news_dashboard.body_fetch import _normalize_crawl4ai_result
    from news_dashboard.content_extraction import assess_extracted_text

    requests: list[str] = []

    async def block_network(route: Any) -> None:
        requests.append(route.request.url)
        await route.abort()

    async def block_page_network(page: Any, **_kwargs: Any) -> None:
        await page.route("**/*", block_network)

    browser = BrowserConfig(headless=True, extra_args=["--host-resolver-rules=MAP * ~NOTFOUND"])
    async with AsyncWebCrawler(config=browser) as crawler:
        crawler.crawler_strategy.set_hook("on_page_context_created", block_page_network)
        result = await crawler.arun(
            url="raw:" + HTML,
            config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS, process_in_browser=True),
        )
    _require(result.success, "Real Crawl4AI browser extraction failed")
    text = _normalize_crawl4ai_result(result)
    quality = assess_extracted_text(text)
    _require("Browser rendered Știri" in text, "Browser did not execute fixture JavaScript")
    _require("community garden" in text, "Article body missing from normalized browser result")
    _require(
        quality.accepted,
        f"Normalized browser body failed application quality gate: {quality!r}; {text!r}",
    )
    _require(not requests, "Offline fixture attempted a network request")
    return {"characters": len(text), "words": quality.word_count, "network_requests": requests}


def main() -> None:
    for name in ("fastuuid", "scipy", "shapely", "litellm", "crawl4ai"):
        importlib.import_module(name)
    from litellm._uuid import uuid4

    from news_dashboard.body_fetch import (
        _crawl4ai_extract_body,
        _normalize_crawl4ai_result,
        _run_crawl4ai,
    )
    from news_dashboard.content_extraction import assess_extracted_text

    _require(uuid4().version == 4, "LiteLLM UUID helper did not generate UUIDv4")
    result = asyncio.run(_browser_smoke())
    # Exercise the application's exact lazy-import adapter as well as its
    # normalization/quality functions. raw: contains no external resources.
    adapted = _run_crawl4ai("raw:" + HTML)
    text = _normalize_crawl4ai_result(adapted)
    _require(adapted.success and "community garden" in text, "Application browser adapter failed")
    _require(assess_extracted_text(text).accepted, "Application adapter body failed quality gate")
    # The public URL stage deliberately remains disabled for SSRF protection.
    _require(
        _crawl4ai_extract_body("https://example.com/article") == ("", "error"),
        "Public URL stage no longer fails closed",
    )
    sys.stdout.write(
        json.dumps(
            {
                "python": sys.version,
                "machine": platform.machine(),
                "platform": platform.system(),
                "versions": {
                    name: version(name)
                    for name in (
                        "crawl4ai",
                        "unclecode-litellm",
                        "fastuuid",
                        "scipy",
                        "shapely",
                        "playwright",
                    )
                },
                "browser": result,
                "application_adapter": "passed",
                "public_url_fail_closed": "passed",
            },
            ensure_ascii=False,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
