from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from news_dashboard.db import connect, init_db, row_to_dict


class SubstackUrlError(ValueError):
    """Raised when a submitted URL cannot identify a Substack publication."""


def list_sources_for_user(
    user_id: int,
    *,
    database_url: str | None = None,
) -> list[dict[str, Any]]:
    """List non-deleted global and user-owned sources with preference metadata."""
    init_db(database_url=database_url)
    with connect(database_url=database_url) as conn:
        rows = conn.execute(
            """
            SELECT s.*,
              CASE WHEN s.owner_user_id IS NULL THEN COALESCE(us.enabled, true)
                   ELSE (s.enabled IS TRUE) END AS user_enabled,
              COALESCE(us.high_priority, false) AS high_priority
            FROM sources s
            LEFT JOIN user_sources us ON us.source_slug = s.slug AND us.user_id = %s
            WHERE (s.owner_user_id IS NULL OR s.owner_user_id = %s)
              AND s.deleted_at IS NULL
            ORDER BY s.category, s.priority DESC, s.name, s.slug
            """,
            (user_id, user_id),
        ).fetchall()

    items: list[dict[str, Any]] = []
    for row in rows:
        item = row_to_dict(row)
        item["subscribed"] = bool(item.pop("user_enabled", 1))
        items.append(item)
    return items


@dataclass(frozen=True)
class SubstackFeed:
    feed_url: str
    suggested_name: str


def normalize_substack_feed_url(submitted_url: str) -> SubstackFeed:
    """Turn a Substack publication or post URL into its canonical RSS feed URL."""
    candidate = submitted_url.strip()
    if not candidate:
        message = "Enter a Substack publication or post link."
        raise SubstackUrlError(message)
    if "://" not in candidate:
        candidate = f"https://{candidate}"

    try:
        parsed = urlsplit(candidate)
    except ValueError as exc:
        message = "Enter a Substack publication or post link."
        raise SubstackUrlError(message) from exc
    hostname = (parsed.hostname or "").lower().rstrip(".")
    labels = hostname.split(".")
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or len(labels) < 2
        or any(not label for label in labels)
    ):
        message = "Enter a Substack publication or post link."
        raise SubstackUrlError(message)

    is_substack_host = labels[-2:] == ["substack", "com"]
    if is_substack_host and (len(labels) != 3 or labels[0] in {"www", "api"}):
        message = "Enter a Substack publication or post link."
        raise SubstackUrlError(message)

    publication = labels[1] if labels[0] == "www" else labels[0]
    suggested_name = publication.replace("-", " ").title()
    return SubstackFeed(
        feed_url=f"https://{hostname}/feed",
        suggested_name=suggested_name,
    )


def add_user_source_preference(
    conn: Any,
    *,
    user_id: int,
    source_slug: str,
    high_priority: bool,
) -> None:
    """Create the current user's preference row for a newly added source."""
    conn.execute(
        """
        INSERT INTO user_sources(user_id, source_slug, enabled, high_priority)
        VALUES (%s, %s, TRUE, %s)
        """,
        (user_id, source_slug, high_priority),
    )


def set_user_source_priority(
    *,
    user_id: int,
    source_slug: str,
    high_priority: bool,
) -> dict[str, Any] | None:
    """Set a user's priority for a visible source, returning None when hidden."""
    init_db()
    with connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM sources
            WHERE slug = %s
              AND (owner_user_id IS NULL OR owner_user_id = %s)
              AND deleted_at IS NULL
            """,
            (source_slug, user_id),
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            """
            INSERT INTO user_sources(user_id, source_slug, enabled, high_priority)
            VALUES (%s, %s, TRUE, %s)
            ON CONFLICT(user_id, source_slug)
            DO UPDATE SET high_priority = excluded.high_priority
            """,
            (user_id, source_slug, high_priority),
        )
    return {**row_to_dict(row), "high_priority": high_priority}


@dataclass(frozen=True)
class SourceDefinition:
    slug: str
    name: str
    url: str
    category: str
    kind: str = "rss_feed"
    priority: int = 50
    enabled: bool = True
    lang: str = "en"
    interest_tags: tuple[str, ...] = ()
    description: str | None = None
    owner_user_id: int | None = None


DEFAULT_SOURCES: list[SourceDefinition] = [
    # ── Python / ecosystem ──────────────────────────────────────────────────
    SourceDefinition(
        "python-insider",
        "Python Insider",
        "https://blog.python.org/feeds/posts/default",
        "python",
        priority=90,
        interest_tags=("python", "product-news"),
    ),
    SourceDefinition(
        "astral-blog",
        "Astral Blog",
        "https://astral.sh/blog/rss.xml",
        "python",
        priority=85,
        interest_tags=("python", "infra"),
    ),
    SourceDefinition(
        "ruff-releases",
        "Ruff releases",
        "https://github.com/astral-sh/ruff/releases.atom",
        "python",
        "github_release_feed",
        85,
        interest_tags=("python", "infra", "model-releases"),
    ),
    SourceDefinition(
        "uv-releases",
        "uv releases",
        "https://github.com/astral-sh/uv/releases.atom",
        "python",
        "github_release_feed",
        85,
        interest_tags=("python", "infra", "model-releases"),
    ),
    SourceDefinition(
        "mypy-releases",
        "mypy releases",
        "https://github.com/python/mypy/releases.atom",
        "python",
        "github_release_feed",
        80,
        interest_tags=("python", "infra", "model-releases"),
    ),
    SourceDefinition(
        "pyright-releases",
        "Pyright releases",
        "https://github.com/microsoft/pyright/releases.atom",
        "python",
        "github_release_feed",
        80,
        interest_tags=("python", "infra", "model-releases"),
    ),
    SourceDefinition(
        "scikit-learn-releases",
        "scikit-learn releases",
        "https://github.com/scikit-learn/scikit-learn/releases.atom",
        "python",
        "github_release_feed",
        75,
        interest_tags=("python", "model-releases"),
    ),
    SourceDefinition(
        "scipy-releases",
        "SciPy releases",
        "https://github.com/scipy/scipy/releases.atom",
        "python",
        "github_release_feed",
        75,
        interest_tags=("python", "model-releases"),
    ),
    SourceDefinition(
        "pytorch-blog",
        "PyTorch Blog",
        "https://pytorch.org/blog/feed.xml",
        "python",
        priority=80,
        interest_tags=("python", "model-releases", "infra"),
    ),
    SourceDefinition(
        "tensorflow-blog",
        "TensorFlow Blog",
        "https://blog.tensorflow.org/feeds/posts/default",
        "python",
        priority=70,
        interest_tags=("python", "model-releases", "infra"),
    ),
    # ── AI / LLM / agents ───────────────────────────────────────────────────
    SourceDefinition(
        "anthropic-news",
        "Anthropic News",
        "https://www.anthropic.com/news",
        "ai-llm",
        "scraped_page",
        90,
        interest_tags=("agents", "model-releases", "evals", "product-news"),
    ),
    SourceDefinition(
        "openai-blog",
        "OpenAI Blog",
        "https://openai.com/news/rss.xml",
        "ai-llm",
        priority=85,
        interest_tags=("agents", "model-releases", "evals", "product-news"),
    ),
    SourceDefinition(
        "deepmind-blog",
        "Google DeepMind Blog",
        "https://deepmind.google/blog/rss.xml",
        "ai-llm",
        priority=85,
        interest_tags=("agents", "model-releases", "evals", "product-news"),
    ),
    SourceDefinition(
        "google-ai-blog",
        "Google AI Blog",
        "https://blog.google/technology/ai/rss/",
        "ai-llm",
        priority=75,
        interest_tags=("model-releases", "product-news", "cloud"),
    ),
    SourceDefinition(
        "huggingface-blog",
        "Hugging Face Blog",
        "https://huggingface.co/blog/feed.xml",
        "ai-llm",
        priority=80,
        interest_tags=("model-releases", "infra", "evals"),
    ),
    SourceDefinition(
        "augment-code-blog",
        "Augment Code Blog",
        "https://www.augmentcode.com/blog/rss.xml",
        "ai-llm",
        priority=70,
        interest_tags=("agents", "product-news"),
    ),
    SourceDefinition(
        "simon-willison",
        "Simon Willison",
        "https://simonwillison.net/atom/everything/",
        "ai-llm",
        priority=85,
        interest_tags=("agents", "model-releases", "evals", "python"),
    ),
    SourceDefinition(
        "latent-space",
        "Latent Space",
        "https://www.latent.space/feed",
        "ai-llm",
        priority=65,
        interest_tags=("agents", "model-releases", "product-news"),
    ),
    SourceDefinition(
        "import-ai",
        "Import AI",
        "https://importai.substack.com/feed",
        "ai-llm",
        priority=65,
        interest_tags=("evals", "model-releases"),
    ),
    SourceDefinition(
        "infoq-ai-ml",
        "InfoQ AI/ML/Data",
        "https://feed.infoq.com/ai-ml-data-eng",
        "ai-llm",
        priority=60,
        interest_tags=("infra", "cloud", "model-releases"),
    ),
    SourceDefinition(
        "cohere-blog",
        "Cohere Blog",
        "https://cohere.com/blog",
        "ai-llm",
        "scraped_page",
        75,
        interest_tags=("agents", "model-releases", "infra", "product-news"),
    ),
    # ── AI research ──────────────────────────────────────────────────────────
    SourceDefinition(
        "arxiv-ai-ml",
        "arXiv AI/ML",
        "https://rss.arxiv.org/rss/cs.AI",
        "ai-research",
        priority=70,
        interest_tags=("evals", "model-releases", "research"),
    ),
    SourceDefinition(
        "mistral-ai-news",
        "Mistral AI News",
        "https://mistral.ai/rss.xml",
        "ai-llm",
        priority=80,
        interest_tags=("agents", "model-releases", "product-news"),
    ),
    SourceDefinition(
        "meta-ai-blog",
        "Meta AI Blog",
        "https://ai.meta.com/blog/",
        "ai-llm",
        "scraped_page",
        80,
        interest_tags=("model-releases", "evals", "infra", "product-news"),
    ),
    SourceDefinition(
        "google-research-blog",
        "Google Research Blog",
        "https://research.google/blog/rss/",
        "ai-research",
        priority=78,
        interest_tags=("evals", "model-releases", "research", "security"),
    ),
    SourceDefinition(
        "berkeley-bair-blog",
        "Berkeley BAIR Blog",
        "https://bair.berkeley.edu/blog/feed.xml",
        "ai-research",
        priority=74,
        interest_tags=("evals", "model-releases", "research"),
    ),
    SourceDefinition(
        "langchain-releases",
        "LangChain releases",
        "https://github.com/langchain-ai/langchain/releases.atom",
        "agents",
        "github_release_feed",
        80,
        interest_tags=("agents", "python", "model-releases"),
    ),
    SourceDefinition(
        "langgraph-releases",
        "LangGraph releases",
        "https://github.com/langchain-ai/langgraph/releases.atom",
        "agents",
        "github_release_feed",
        85,
        interest_tags=("agents", "python", "model-releases"),
    ),
    SourceDefinition(
        "langfuse-releases",
        "Langfuse releases",
        "https://github.com/langfuse/langfuse/releases.atom",
        "agents",
        "github_release_feed",
        80,
        interest_tags=("agents", "infra", "model-releases"),
    ),
    # ── Security ────────────────────────────────────────────────────────────
    SourceDefinition(
        "trail-of-bits-blog",
        "Trail of Bits Blog",
        "https://blog.trailofbits.com/feed/",
        "security",
        priority=76,
        interest_tags=("security", "infra", "software-development"),
    ),
    SourceDefinition(
        "github-security-lab",
        "GitHub Security Lab",
        "https://github.blog/tag/github-security-lab/feed/",
        "security",
        priority=74,
        interest_tags=("security", "infra", "product-news"),
    ),
    SourceDefinition(
        "google-project-zero",
        "Google Project Zero",
        # Summary feed with a post cap: the default feed embeds full post bodies
        # and exceeds the 2 MiB fetch cap (~13 MiB); the summary feed is a few KB.
        "https://googleprojectzero.blogspot.com/feeds/posts/summary?alt=rss&max-results=25",
        "security",
        priority=82,
        interest_tags=("security", "research"),
    ),
    # ── Cloud / infra ────────────────────────────────────────────────────────
    SourceDefinition(
        "kubernetes-blog",
        "Kubernetes Blog",
        "https://kubernetes.io/feed.xml",
        "cloud-infra",
        priority=65,
        interest_tags=("cloud", "infra"),
    ),
    SourceDefinition(
        "docker-blog",
        "Docker Blog",
        "https://www.docker.com/blog/feed/",
        "cloud-infra",
        priority=65,
        interest_tags=("cloud", "infra"),
    ),
    SourceDefinition(
        "aws-ml-blog",
        "AWS Machine Learning Blog",
        "https://aws.amazon.com/blogs/machine-learning/feed/",
        "cloud-infra",
        priority=60,
        interest_tags=("cloud", "infra", "model-releases"),
    ),
    SourceDefinition(
        "chrome-developers-blog",
        "Chrome Developers Blog",
        "https://developer.chrome.com/static/blog/feed.xml",
        "web",
        priority=70,
        interest_tags=("web", "frontend", "product-news"),
    ),
    SourceDefinition(
        "cloudflare-blog",
        "Cloudflare Blog",
        "https://blog.cloudflare.com/rss/",
        "cloud-infra",
        priority=70,
        interest_tags=("cloud", "infra", "security"),
    ),
    SourceDefinition(
        "web-dev-blog",
        "web.dev Blog",
        "https://web.dev/feed.xml",
        "web",
        priority=70,
        interest_tags=("web", "frontend", "performance"),
    ),
    # ── Engineering ──────────────────────────────────────────────────────────
    SourceDefinition(
        "pragmatic-engineer",
        "The Pragmatic Engineer",
        "https://newsletter.pragmaticengineer.com/feed",
        "engineering",
        priority=60,
        interest_tags=("product-news", "infra"),
    ),
    SourceDefinition(
        "github-changelog",
        "GitHub Changelog",
        "https://github.blog/changelog/feed/",
        "engineering",
        priority=65,
        interest_tags=("product-news", "infra"),
    ),
    SourceDefinition(
        "github-engineering",
        "GitHub Engineering",
        "https://github.blog/engineering/feed/",
        "engineering",
        priority=55,
        interest_tags=("infra", "cloud"),
    ),
    SourceDefinition(
        "martin-fowler",
        "Martin Fowler",
        "https://martinfowler.com/feed.atom",
        "engineering",
        priority=65,
        interest_tags=("infra", "software-development", "architecture"),
    ),
    SourceDefinition(
        "netflix-techblog",
        "Netflix TechBlog",
        "https://netflixtechblog.com/feed",
        "engineering",
        priority=68,
        interest_tags=("infra", "software-development", "cloud"),
    ),
    # ── Developer tools ──────────────────────────────────────────────────────
    SourceDefinition(
        "typescript-blog",
        "TypeScript Blog",
        "https://devblogs.microsoft.com/typescript/feed/",
        "developer-tools",
        priority=78,
        interest_tags=("programming", "frontend", "software-development"),
    ),
    SourceDefinition(
        "v8-blog",
        "V8 Blog",
        "https://v8.dev/blog.atom",
        "developer-tools",
        priority=72,
        interest_tags=("javascript", "performance", "frontend"),
    ),
    # ── Trending / repositories ───────────────────────────────────────────────
    SourceDefinition(
        "hacker-news-best",
        "Hacker News Best",
        "https://hnrss.org/best",
        "trending",
        "trending_feed",
        55,
    ),
    SourceDefinition(
        "hacker-news-ai",
        "Hacker News AI",
        "https://hnrss.org/newest?q=AI",
        "trending",
        "trending_feed",
        55,
    ),
    SourceDefinition(
        "github-trending-all",
        "GitHub Trending All",
        "https://mshibanami.github.io/GitHubTrendingRSS/daily/all.xml",
        "repositories",
        "trending_feed",
        60,
    ),
    SourceDefinition(
        "github-trending-python",
        "GitHub Trending Python",
        "https://mshibanami.github.io/GitHubTrendingRSS/daily/python.xml",
        "repositories",
        "trending_feed",
        70,
    ),
    SourceDefinition(
        "github-trending-typescript",
        "GitHub Trending TypeScript",
        "https://mshibanami.github.io/GitHubTrendingRSS/daily/typescript.xml",
        "repositories",
        "trending_feed",
        60,
    ),
    # ── X / Twitter — AI companies & individuals (via Nitter RSS) ──────────────
    # Handles verified June 2026. Nitter instances are community-run; if feeds
    # stop working update _NITTER_INSTANCES in ingest.py.
    #
    # Company accounts
    SourceDefinition(
        "x-anthropicai",
        "Anthropic (@AnthropicAI)",
        "https://x.com/AnthropicAI",
        "ai-social",
        "nitter_feed",
        80,
    ),
    SourceDefinition(
        "x-openai",
        "OpenAI (@OpenAI)",
        "https://x.com/OpenAI",
        "ai-social",
        "nitter_feed",
        80,
    ),
    SourceDefinition(
        "x-googledeepmind",
        "Google DeepMind (@GoogleDeepMind)",
        "https://x.com/GoogleDeepMind",
        "ai-social",
        "nitter_feed",
        80,
    ),
    SourceDefinition(
        "x-aiatmeta",
        "Meta AI (@AIatMeta)",
        "https://x.com/AIatMeta",
        "ai-social",
        "nitter_feed",
        75,
    ),
    SourceDefinition(
        "x-mistralai",
        "Mistral AI (@MistralAI)",
        "https://x.com/MistralAI",
        "ai-social",
        "nitter_feed",
        75,
    ),
    SourceDefinition(
        "x-huggingface",
        "Hugging Face (@huggingface)",
        "https://x.com/huggingface",
        "ai-social",
        "nitter_feed",
        75,
    ),
    SourceDefinition(
        "x-xai",
        "xAI (@xai)",
        "https://x.com/xai",
        "ai-social",
        "nitter_feed",
        75,
    ),
    # Individuals — lab founders & research leaders
    SourceDefinition(
        "x-darioamodei",
        "Dario Amodei (@DarioAmodei)",
        "https://x.com/DarioAmodei",
        "ai-social",
        "nitter_feed",
        85,
    ),
    SourceDefinition(
        "x-jackclarksf",
        "Jack Clark (@jackclarksf)",
        "https://x.com/jackclarksf",
        "ai-social",
        "nitter_feed",
        70,
    ),
    SourceDefinition(
        "x-sama",
        "Sam Altman (@sama)",
        "https://x.com/sama",
        "ai-social",
        "nitter_feed",
        85,
    ),
    SourceDefinition(
        "x-gdb",
        "Greg Brockman (@gdb)",
        "https://x.com/gdb",
        "ai-social",
        "nitter_feed",
        70,
    ),
    SourceDefinition(
        "x-demishassabis",
        "Demis Hassabis (@demishassabis)",
        "https://x.com/demishassabis",
        "ai-social",
        "nitter_feed",
        85,
    ),
    SourceDefinition(
        "x-ylecun",
        "Yann LeCun (@ylecun)",
        "https://x.com/ylecun",
        "ai-social",
        "nitter_feed",
        80,
    ),
    SourceDefinition(
        "x-arthurmensch",
        "Arthur Mensch (@arthurmensch)",
        "https://x.com/arthurmensch",
        "ai-social",
        "nitter_feed",
        75,
    ),
    SourceDefinition(
        "x-karpathy",
        "Andrej Karpathy (@karpathy)",
        "https://x.com/karpathy",
        "ai-social",
        "nitter_feed",
        85,
    ),
    SourceDefinition(
        "x-clementdelangue",
        "Clement Delangue (@ClementDelangue)",
        "https://x.com/ClementDelangue",
        "ai-social",
        "nitter_feed",
        75,
    ),
    SourceDefinition(
        "x-theo",
        "Theo (@theo)",
        "https://x.com/theo",
        "ai-social",
        "nitter_feed",
        65,
    ),
    # ── Reddit feeds ──────────────────────────────────────────────────────────────
    SourceDefinition(
        "reddit-python",
        "Reddit r/Python",
        "https://www.reddit.com/r/python/",
        "python",
        "reddit_feed",
        80,
        interest_tags=("python", "programming"),
    ),
    SourceDefinition(
        "reddit-machinelearning",
        "Reddit r/MachineLearning",
        "https://www.reddit.com/r/MachineLearning/",
        "ai-llm",
        "reddit_feed",
        75,
        interest_tags=("ai", "ml", "research"),
    ),
    SourceDefinition(
        "reddit-programming",
        "Reddit r/Programming",
        "https://www.reddit.com/r/programming/",
        "python",
        "reddit_feed",
        70,
        interest_tags=("programming", "software-development"),
    ),
    # ── Lobsters feeds ───────────────────────────────────────────────────────────
    SourceDefinition(
        "lobsters",
        "Lobsters",
        "https://lobste.rs/rss",
        "tech",
        "lobsters_feed",
        60,
        interest_tags=("programming", "tech", "startups"),
    ),
    SourceDefinition(
        "lobsters-web",
        "Lobsters Web",
        "https://lobste.rs/t/web.rss",
        "web",
        "lobsters_feed",
        55,
        interest_tags=("web", "frontend", "css"),
    ),
    SourceDefinition(
        "lobsters-ruby",
        "Lobsters Ruby",
        "https://lobste.rs/t/ruby.rss",
        "ruby",
        "lobsters_feed",
        55,
        interest_tags=("ruby", "rails", "backend"),
    ),
    # ── Mastodon feeds ───────────────────────────────────────────────────────────
    SourceDefinition(
        "mastodon-tech",
        "Mastodon Technology",
        "https://mastodon.social/tags/technology.rss",
        "tech",
        "mastodon_feed",
        60,
        interest_tags=("tech", "gadgets", "innovation"),
    ),
    SourceDefinition(
        "mastodon-webdev",
        "Mastodon WebDev",
        "https://mastodon.social/tags/webdev.rss",
        "web",
        "mastodon_feed",
        55,
        interest_tags=("web", "development", "javascript"),
    ),
]
