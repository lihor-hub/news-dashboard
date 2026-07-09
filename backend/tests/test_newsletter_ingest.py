"""Tests for IMAP newsletter ingestion (backend/news_dashboard/newsletter_ingest.py).

Uses a fake IMAP client (no live network) injected via ``client_factory``.
"""

from __future__ import annotations

from email.message import EmailMessage
from typing import Any

import pytest

from news_dashboard.db import connect, init_db, row_to_dict
from news_dashboard.newsletter_ingest import (
    extract_plus_tag,
    imap_config,
    imap_configured,
    max_message_bytes,
    poll_minutes,
    poll_newsletters,
)

# ── fake IMAP client ─────────────────────────────────────────────────────────


class FakeImapClient:
    """Minimal stand-in for imaplib.IMAP4_SSL, driven by a list of raw messages."""

    def __init__(self, messages: list[bytes]) -> None:
        # message number (1-indexed, as IMAP does) -> (raw bytes, seen flag)
        self.messages: dict[int, list[Any]] = {
            i + 1: [raw, False] for i, raw in enumerate(messages)
        }
        self.logged_out = False
        self.selected: str | None = None

    def login(self, _user: str, _password: str) -> tuple[str, list[bytes]]:
        return "OK", [b""]

    def select(self, mailbox: str) -> tuple[str, list[bytes]]:
        self.selected = mailbox
        return "OK", [b"1"]

    def search(self, _charset: str | None, *_criteria: str) -> tuple[str, list[bytes]]:
        unseen = [str(num).encode() for num, (_raw, seen) in self.messages.items() if not seen]
        return "OK", [b" ".join(unseen)]

    def fetch(self, message_set: str, _message_parts: str) -> tuple[str, list[Any]]:
        num = int(message_set)
        raw, _seen = self.messages[num]
        header = f"{num} (RFC822 {{{len(raw)}}}".encode()
        return "OK", [(header, raw)]

    def store(self, message_set: str, _command: str, flags: str) -> tuple[str, list[bytes]]:
        num = int(message_set)
        if flags == r"\Seen":
            self.messages[num][1] = True
        return "OK", [b""]

    def logout(self) -> tuple[str, list[bytes]]:
        self.logged_out = True
        return "OK", [b""]


def _make_factory(client: FakeImapClient) -> Any:
    return lambda _config: client


def _html_message(*, to: str, subject: str, sender: str, html_body: str, message_id: str) -> bytes:
    msg = EmailMessage()
    msg["Message-ID"] = message_id
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg["Date"] = "Mon, 01 Jan 2024 09:00:00 +0000"
    msg.set_content("plain text fallback")
    msg.add_alternative(html_body, subtype="html")
    return bytes(msg)


def _plain_message(*, to: str, subject: str, sender: str, body: str, message_id: str) -> bytes:
    msg = EmailMessage()
    msg["Message-ID"] = message_id
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg["Date"] = "Mon, 01 Jan 2024 09:00:00 +0000"
    msg.set_content(body)
    return bytes(msg)


# ── plus-address -> user mapping ─────────────────────────────────────────────


def test_extract_plus_tag_matches_username() -> None:
    assert extract_plus_tag(["inbox+alice@example.com"]) == "alice"


def test_extract_plus_tag_lowercases() -> None:
    assert extract_plus_tag(["Inbox+Alice@example.com"]) == "alice"


def test_extract_plus_tag_scans_multiple_recipients() -> None:
    addrs = ["someone-else@example.com", "inbox+bob@example.com"]
    assert extract_plus_tag(addrs) == "bob"


def test_extract_plus_tag_returns_none_without_plus() -> None:
    assert extract_plus_tag(["inbox@example.com"]) is None


def test_extract_plus_tag_returns_none_for_empty_list() -> None:
    assert extract_plus_tag([]) is None


# ── config / inertness ───────────────────────────────────────────────────────


def test_imap_configured_false_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEWSLETTER_IMAP_HOST", raising=False)
    monkeypatch.delenv("NEWSLETTER_IMAP_USERNAME", raising=False)
    monkeypatch.delenv("NEWSLETTER_IMAP_PASSWORD", raising=False)
    assert imap_configured() is False
    assert imap_config() is None


def test_imap_configured_requires_all_three(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSLETTER_IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("NEWSLETTER_IMAP_USERNAME", "inbox@example.com")
    monkeypatch.delenv("NEWSLETTER_IMAP_PASSWORD", raising=False)
    assert imap_configured() is False


def test_imap_configured_true_with_full_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSLETTER_IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("NEWSLETTER_IMAP_USERNAME", "inbox@example.com")
    monkeypatch.setenv("NEWSLETTER_IMAP_PASSWORD", "secret")
    config = imap_config()
    assert config is not None
    assert config.host == "imap.example.com"
    assert config.port == 993
    assert config.folder == "INBOX"


def test_poll_minutes_defaults_to_15(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEWSLETTER_POLL_MINUTES", raising=False)
    assert poll_minutes() == 15


def test_max_message_bytes_defaults_to_5mib(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEWSLETTER_MAX_MESSAGE_BYTES", raising=False)
    assert max_message_bytes() == 5 * 1024 * 1024


def test_max_message_bytes_respects_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSLETTER_MAX_MESSAGE_BYTES", "1024")
    assert max_message_bytes() == 1024


def test_poll_newsletters_noop_without_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEWSLETTER_IMAP_HOST", raising=False)
    monkeypatch.delenv("NEWSLETTER_IMAP_USERNAME", raising=False)
    monkeypatch.delenv("NEWSLETTER_IMAP_PASSWORD", raising=False)

    called = False

    def _factory(_config: Any) -> Any:
        nonlocal called
        called = True
        message = "should not connect when not configured"
        raise AssertionError(message)

    result = poll_newsletters(client_factory=_factory)
    assert result == 0
    assert called is False


# ── DB-backed ingestion tests ─────────────────────────────────────────────────


def _configure_imap_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSLETTER_IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("NEWSLETTER_IMAP_USERNAME", "inbox@example.com")
    monkeypatch.setenv("NEWSLETTER_IMAP_PASSWORD", "secret")


def _make_user(database_url: str, username: str) -> int:
    with connect(database_url=database_url) as conn:
        row = conn.execute(
            "INSERT INTO users(username, password_hash) VALUES (%s, %s) RETURNING id",
            (username, "test-hash"),
        ).fetchone()
    assert row is not None
    return int(row_to_dict(row)["id"])


def test_html_newsletter_becomes_private_article(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    _configure_imap_env(monkeypatch)
    init_db(database_url=pg_clean)
    alice_id = _make_user(pg_clean, "alice")
    _make_user(pg_clean, "bob")

    raw = _html_message(
        to="inbox+alice@example.com",
        subject="Weekly Roundup",
        sender="Cool Newsletter <news@coolnewsletter.com>",
        html_body="<p>Hello <b>world</b></p>",
        message_id="<msg-1@coolnewsletter.com>",
    )
    client = FakeImapClient([raw])

    processed = poll_newsletters(db_path=pg_clean, client_factory=_make_factory(client))
    assert processed == 1

    with connect(database_url=pg_clean) as conn:
        articles = conn.execute("SELECT title, summary, source_slug, kind FROM articles").fetchall()
        sources = conn.execute(
            "SELECT slug, kind, owner_user_id FROM sources WHERE owner_user_id IS NOT NULL"
        ).fetchall()

    assert len(articles) == 1
    article = row_to_dict(articles[0])
    assert article["title"] == "Weekly Roundup"
    assert "Hello" in article["summary"]
    assert "world" in article["summary"]
    assert "<b>" not in article["summary"]
    assert article["kind"] == "newsletter"

    assert len(sources) == 1
    source = row_to_dict(sources[0])
    assert source["kind"] == "newsletter"
    assert source["owner_user_id"] == alice_id
    assert article["source_slug"] == source["slug"]

    # message marked \Seen after successful insert
    assert client.messages[1][1] is True


def test_plain_text_newsletter_ingests(monkeypatch: pytest.MonkeyPatch, pg_clean: str) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    _configure_imap_env(monkeypatch)
    init_db(database_url=pg_clean)
    _make_user(pg_clean, "alice")

    raw = _plain_message(
        to="inbox+alice@example.com",
        subject="Plain Update",
        sender="Plain Sender <plain@example.com>",
        body="Just plain text, no HTML here.",
        message_id="<msg-plain-1@example.com>",
    )
    client = FakeImapClient([raw])

    processed = poll_newsletters(db_path=pg_clean, client_factory=_make_factory(client))
    assert processed == 1

    with connect(database_url=pg_clean) as conn:
        rows = conn.execute("SELECT title, summary FROM articles").fetchall()
    assert len(rows) == 1
    row = row_to_dict(rows[0])
    assert row["title"] == "Plain Update"
    assert "Just plain text" in row["summary"]


def test_repolling_same_message_id_does_not_duplicate(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    _configure_imap_env(monkeypatch)
    init_db(database_url=pg_clean)
    _make_user(pg_clean, "alice")

    raw = _html_message(
        to="inbox+alice@example.com",
        subject="Same Message",
        sender="Sender <sender@example.com>",
        html_body="<p>Body</p>",
        message_id="<duplicate-msg@example.com>",
    )

    # First poll: message is UNSEEN, gets ingested and marked \Seen.
    client1 = FakeImapClient([raw])
    processed1 = poll_newsletters(db_path=pg_clean, client_factory=_make_factory(client1))
    assert processed1 == 1

    # Simulate re-poll of the same underlying message (e.g. moved back to
    # UNSEEN, or fetched again some other way) by feeding the same raw bytes
    # through a fresh fake client.
    client2 = FakeImapClient([raw])
    processed2 = poll_newsletters(db_path=pg_clean, client_factory=_make_factory(client2))
    assert processed2 == 1  # still "processed" (handled), but no new article

    with connect(database_url=pg_clean) as conn:
        count = conn.execute("SELECT COUNT(*) AS n FROM articles").fetchone()
    assert row_to_dict(count)["n"] == 1


def test_unknown_user_tag_is_skipped(monkeypatch: pytest.MonkeyPatch, pg_clean: str) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    _configure_imap_env(monkeypatch)
    init_db(database_url=pg_clean)
    _make_user(pg_clean, "alice")

    raw = _html_message(
        to="inbox+nosuchuser@example.com",
        subject="Orphan Newsletter",
        sender="Sender <sender@example.com>",
        html_body="<p>Body</p>",
        message_id="<orphan-msg@example.com>",
    )
    client = FakeImapClient([raw])

    processed = poll_newsletters(db_path=pg_clean, client_factory=_make_factory(client))
    assert processed == 1  # handled (marked seen), but no article created

    with connect(database_url=pg_clean) as conn:
        count = conn.execute("SELECT COUNT(*) AS n FROM articles").fetchone()
    assert row_to_dict(count)["n"] == 0
    # Still marked seen so we don't retry a message we can't route forever.
    assert client.messages[1][1] is True


def test_missing_plus_tag_is_skipped(monkeypatch: pytest.MonkeyPatch, pg_clean: str) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    _configure_imap_env(monkeypatch)
    init_db(database_url=pg_clean)
    _make_user(pg_clean, "alice")

    raw = _html_message(
        to="inbox@example.com",
        subject="No Tag Newsletter",
        sender="Sender <sender@example.com>",
        html_body="<p>Body</p>",
        message_id="<no-tag-msg@example.com>",
    )
    client = FakeImapClient([raw])

    processed = poll_newsletters(db_path=pg_clean, client_factory=_make_factory(client))
    assert processed == 1

    with connect(database_url=pg_clean) as conn:
        count = conn.execute("SELECT COUNT(*) AS n FROM articles").fetchone()
    assert row_to_dict(count)["n"] == 0


def test_private_source_invisible_to_other_users(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    _configure_imap_env(monkeypatch)
    init_db(database_url=pg_clean)
    alice_id = _make_user(pg_clean, "alice")
    bob_id = _make_user(pg_clean, "bob")

    raw = _html_message(
        to="inbox+alice@example.com",
        subject="Private For Alice",
        sender="Sender <sender@example.com>",
        html_body="<p>Body</p>",
        message_id="<private-msg@example.com>",
    )
    client = FakeImapClient([raw])
    poll_newsletters(db_path=pg_clean, client_factory=_make_factory(client))

    from news_dashboard.ingest import list_articles

    alice_articles = list_articles(db_path=pg_clean, user_id=alice_id)
    bob_articles = list_articles(db_path=pg_clean, user_id=bob_id)

    assert any(a["title"] == "Private For Alice" for a in alice_articles)
    assert not any(a["title"] == "Private For Alice" for a in bob_articles)


def test_two_newsletters_same_sender_share_one_source(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    _configure_imap_env(monkeypatch)
    init_db(database_url=pg_clean)
    _make_user(pg_clean, "alice")

    raw1 = _html_message(
        to="inbox+alice@example.com",
        subject="Issue 1",
        sender="Cool Newsletter <news@coolnewsletter.com>",
        html_body="<p>One</p>",
        message_id="<issue-1@coolnewsletter.com>",
    )
    raw2 = _html_message(
        to="inbox+alice@example.com",
        subject="Issue 2",
        sender="Cool Newsletter <news@coolnewsletter.com>",
        html_body="<p>Two</p>",
        message_id="<issue-2@coolnewsletter.com>",
    )
    client = FakeImapClient([raw1, raw2])
    processed = poll_newsletters(db_path=pg_clean, client_factory=_make_factory(client))
    assert processed == 2

    with connect(database_url=pg_clean) as conn:
        sources = conn.execute(
            "SELECT slug FROM sources WHERE owner_user_id IS NOT NULL"
        ).fetchall()
        articles = conn.execute("SELECT source_slug FROM articles").fetchall()

    assert len(sources) == 1
    slugs = {row_to_dict(a)["source_slug"] for a in articles}
    assert slugs == {row_to_dict(sources[0])["slug"]}


def test_same_sender_different_users_get_separate_sources(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str
) -> None:
    """Two users subscribing to the same newsletter sender must not collide on

    one shared source row: sources.slug is a global primary key, so the slug
    must be scoped per owner_user_id, otherwise the second user's articles
    would silently end up attributed to the first user's private source.
    """
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    _configure_imap_env(monkeypatch)
    init_db(database_url=pg_clean)
    alice_id = _make_user(pg_clean, "alice")
    bob_id = _make_user(pg_clean, "bob")

    raw_alice = _html_message(
        to="inbox+alice@example.com",
        subject="For Alice",
        sender="Cool Newsletter <news@coolnewsletter.com>",
        html_body="<p>Alice's copy</p>",
        message_id="<alice-issue@coolnewsletter.com>",
    )
    raw_bob = _html_message(
        to="inbox+bob@example.com",
        subject="For Bob",
        sender="Cool Newsletter <news@coolnewsletter.com>",
        html_body="<p>Bob's copy</p>",
        message_id="<bob-issue@coolnewsletter.com>",
    )
    client = FakeImapClient([raw_alice, raw_bob])
    processed = poll_newsletters(db_path=pg_clean, client_factory=_make_factory(client))
    assert processed == 2

    from news_dashboard.ingest import list_articles

    alice_articles = list_articles(db_path=pg_clean, user_id=alice_id)
    bob_articles = list_articles(db_path=pg_clean, user_id=bob_id)

    assert any(a["title"] == "For Alice" for a in alice_articles)
    assert not any(a["title"] == "For Bob" for a in alice_articles)
    assert any(a["title"] == "For Bob" for a in bob_articles)
    assert not any(a["title"] == "For Alice" for a in bob_articles)

    with connect(database_url=pg_clean) as conn:
        sources = conn.execute(
            "SELECT slug, owner_user_id FROM sources WHERE owner_user_id IS NOT NULL"
        ).fetchall()
    owners = {row_to_dict(s)["owner_user_id"] for s in sources}
    assert owners == {alice_id, bob_id}


def test_failed_message_left_unread(monkeypatch: pytest.MonkeyPatch, pg_clean: str) -> None:
    """A message that raises during fetch is left unread (not marked \\Seen)."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    _configure_imap_env(monkeypatch)
    init_db(database_url=pg_clean)
    _make_user(pg_clean, "alice")

    class BrokenFetchClient(FakeImapClient):
        # Parameter name matches the base method (ty enforces Liskov param-name
        # compatibility); ruff's unused-argument check is suppressed instead.
        def fetch(self, message_set: str, _message_parts: str) -> tuple[str, list[Any]]:  # noqa: ARG002
            message = "network blip"
            raise RuntimeError(message)

    raw = _html_message(
        to="inbox+alice@example.com",
        subject="Will Fail",
        sender="Sender <sender@example.com>",
        html_body="<p>Body</p>",
        message_id="<fail-msg@example.com>",
    )
    client = BrokenFetchClient([raw])

    processed = poll_newsletters(db_path=pg_clean, client_factory=_make_factory(client))
    assert processed == 0
    assert client.messages[1][1] is False  # left unread for retry


# ── oversized message handling ───────────────────────────────────────────────


def test_oversized_message_is_skipped_and_marked_seen(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    _configure_imap_env(monkeypatch)
    monkeypatch.setenv("NEWSLETTER_MAX_MESSAGE_BYTES", "100")
    init_db(database_url=pg_clean)
    _make_user(pg_clean, "alice")

    raw = _html_message(
        to="inbox+alice@example.com",
        subject="Huge Newsletter",
        sender="Sender <sender@example.com>",
        html_body="<p>" + ("x" * 1000) + "</p>",
        message_id="<huge-msg@example.com>",
    )
    assert len(raw) > 100
    client = FakeImapClient([raw])

    processed = poll_newsletters(db_path=pg_clean, client_factory=_make_factory(client))
    assert processed == 1  # handled (marked seen), but no article created

    with connect(database_url=pg_clean) as conn:
        count = conn.execute("SELECT COUNT(*) AS n FROM articles").fetchone()
    assert row_to_dict(count)["n"] == 0
    # Marked seen so the same oversized message isn't retried on every poll.
    assert client.messages[1][1] is True


def test_oversized_message_never_reaches_message_from_bytes(
    monkeypatch: pytest.MonkeyPatch, pg_clean: str
) -> None:
    """Oversized messages must be rejected by their reported size alone, before

    ``message_from_bytes()`` or any body-extraction work runs on them.
    """
    import news_dashboard.newsletter_ingest as newsletter_ingest_module

    monkeypatch.setenv("DATABASE_URL", pg_clean)
    _configure_imap_env(monkeypatch)
    monkeypatch.setenv("NEWSLETTER_MAX_MESSAGE_BYTES", "100")
    init_db(database_url=pg_clean)
    _make_user(pg_clean, "alice")

    def _boom(_raw: bytes) -> Any:
        message = "message_from_bytes should not be called for oversized messages"
        raise AssertionError(message)

    monkeypatch.setattr(newsletter_ingest_module, "message_from_bytes", _boom)

    raw = _html_message(
        to="inbox+alice@example.com",
        subject="Huge Newsletter",
        sender="Sender <sender@example.com>",
        html_body="<p>" + ("x" * 1000) + "</p>",
        message_id="<huge-msg-2@example.com>",
    )
    client = FakeImapClient([raw])

    processed = poll_newsletters(db_path=pg_clean, client_factory=_make_factory(client))
    assert processed == 1


def test_message_within_limit_still_ingests(monkeypatch: pytest.MonkeyPatch, pg_clean: str) -> None:
    """A normal-sized message is unaffected when a size limit is configured."""
    monkeypatch.setenv("DATABASE_URL", pg_clean)
    _configure_imap_env(monkeypatch)
    monkeypatch.setenv("NEWSLETTER_MAX_MESSAGE_BYTES", "1000000")
    init_db(database_url=pg_clean)
    _make_user(pg_clean, "alice")

    raw = _html_message(
        to="inbox+alice@example.com",
        subject="Normal Newsletter",
        sender="Sender <sender@example.com>",
        html_body="<p>Hello world</p>",
        message_id="<normal-msg@example.com>",
    )
    client = FakeImapClient([raw])

    processed = poll_newsletters(db_path=pg_clean, client_factory=_make_factory(client))
    assert processed == 1

    with connect(database_url=pg_clean) as conn:
        count = conn.execute("SELECT COUNT(*) AS n FROM articles").fetchone()
    assert row_to_dict(count)["n"] == 1
