from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceDefinition:
    slug: str
    name: str
    url: str
    category: str
    kind: str = "rss_feed"
    priority: int = 50
    enabled: bool = True


DEFAULT_SOURCES: list[SourceDefinition] = [
    # ── Python / ecosystem ──────────────────────────────────────────────────
    SourceDefinition(
        "python-insider",
        "Python Insider",
        "https://blog.python.org/feeds/posts/default",
        "python",
        priority=90,
    ),
    SourceDefinition(
        "astral-blog", "Astral Blog", "https://astral.sh/blog/rss.xml", "python", priority=85
    ),
    SourceDefinition(
        "ruff-releases",
        "Ruff releases",
        "https://github.com/astral-sh/ruff/releases.atom",
        "python",
        "github_release_feed",
        85,
    ),
    SourceDefinition(
        "uv-releases",
        "uv releases",
        "https://github.com/astral-sh/uv/releases.atom",
        "python",
        "github_release_feed",
        85,
    ),
    SourceDefinition(
        "mypy-releases",
        "mypy releases",
        "https://github.com/python/mypy/releases.atom",
        "python",
        "github_release_feed",
        80,
    ),
    SourceDefinition(
        "pyright-releases",
        "Pyright releases",
        "https://github.com/microsoft/pyright/releases.atom",
        "python",
        "github_release_feed",
        80,
    ),
    SourceDefinition(
        "scikit-learn-releases",
        "scikit-learn releases",
        "https://github.com/scikit-learn/scikit-learn/releases.atom",
        "python",
        "github_release_feed",
        75,
    ),
    SourceDefinition(
        "scipy-releases",
        "SciPy releases",
        "https://github.com/scipy/scipy/releases.atom",
        "python",
        "github_release_feed",
        75,
    ),
    SourceDefinition(
        "pytorch-blog", "PyTorch Blog", "https://pytorch.org/blog/feed.xml", "python", priority=80
    ),
    SourceDefinition(
        "tensorflow-blog",
        "TensorFlow Blog",
        "https://blog.tensorflow.org/feeds/posts/default",
        "python",
        priority=70,
    ),
    # ── AI / LLM / agents ───────────────────────────────────────────────────
    SourceDefinition(
        "anthropic-news",
        "Anthropic News",
        "https://www.anthropic.com/news",
        "ai-llm",
        "scraped_page",
        90,
    ),
    SourceDefinition(
        "openai-blog", "OpenAI Blog", "https://openai.com/news/rss.xml", "ai-llm", priority=85
    ),
    SourceDefinition(
        "google-ai-blog",
        "Google AI Blog",
        "https://blog.google/technology/ai/rss/",
        "ai-llm",
        priority=75,
    ),
    SourceDefinition(
        "huggingface-blog",
        "Hugging Face Blog",
        "https://huggingface.co/blog/feed.xml",
        "ai-llm",
        priority=80,
    ),
    SourceDefinition(
        "augment-code-blog",
        "Augment Code Blog",
        "https://www.augmentcode.com/blog/rss.xml",
        "ai-llm",
        priority=70,
    ),
    SourceDefinition(
        "simon-willison",
        "Simon Willison",
        "https://simonwillison.net/atom/everything/",
        "ai-llm",
        priority=85,
    ),
    SourceDefinition(
        "latent-space", "Latent Space", "https://www.latent.space/feed", "ai-llm", priority=65
    ),
    SourceDefinition(
        "import-ai", "Import AI", "https://importai.substack.com/feed", "ai-llm", priority=65
    ),
    SourceDefinition(
        "infoq-ai-ml",
        "InfoQ AI/ML/Data",
        "https://feed.infoq.com/ai-ml-data-eng",
        "ai-llm",
        priority=60,
    ),
    SourceDefinition(
        "langchain-releases",
        "LangChain releases",
        "https://github.com/langchain-ai/langchain/releases.atom",
        "agents",
        "github_release_feed",
        80,
    ),
    SourceDefinition(
        "langgraph-releases",
        "LangGraph releases",
        "https://github.com/langchain-ai/langgraph/releases.atom",
        "agents",
        "github_release_feed",
        85,
    ),
    SourceDefinition(
        "langfuse-releases",
        "Langfuse releases",
        "https://github.com/langfuse/langfuse/releases.atom",
        "agents",
        "github_release_feed",
        80,
    ),
    # ── Cloud / infra ────────────────────────────────────────────────────────
    SourceDefinition(
        "kubernetes-blog",
        "Kubernetes Blog",
        "https://kubernetes.io/feed.xml",
        "cloud-infra",
        priority=65,
    ),
    SourceDefinition(
        "docker-blog",
        "Docker Blog",
        "https://www.docker.com/blog/feed/",
        "cloud-infra",
        priority=65,
    ),
    SourceDefinition(
        "aws-ml-blog",
        "AWS Machine Learning Blog",
        "https://aws.amazon.com/blogs/machine-learning/feed/",
        "cloud-infra",
        priority=60,
    ),
    # ── Engineering ──────────────────────────────────────────────────────────
    SourceDefinition(
        "pragmatic-engineer",
        "The Pragmatic Engineer",
        "https://newsletter.pragmaticengineer.com/feed",
        "engineering",
        priority=60,
    ),
    SourceDefinition(
        "github-changelog",
        "GitHub Changelog",
        "https://github.blog/changelog/feed/",
        "engineering",
        priority=65,
    ),
    SourceDefinition(
        "github-engineering",
        "GitHub Engineering",
        "https://github.blog/engineering/feed/",
        "engineering",
        priority=55,
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
]
