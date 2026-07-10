"""Ingest email newsletters via IMAP into per-user private sources.

v1 scope: a single shared IMAP mailbox using plus-addressing
(``inbox+<username>@domain``) to route each newsletter to the right user's
private, ``newsletter``-kind source. Uses only the stdlib ``imaplib`` /
``email`` modules — no new heavy dependencies.

The whole module is inert unless ``NEWSLETTER_IMAP_HOST``,
``NEWSLETTER_IMAP_USERNAME`` and ``NEWSLETTER_IMAP_PASSWORD`` are all set;
see :func:`imap_configured` and :func:`poll_newsletters`.
"""

from __future__ import annotations

import imaplib
import logging
import os
import re
from dataclasses import dataclass
from datetime import timezone
from email import message_from_bytes
from email.message import Message
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path
from typing import Any, Protocol

from news_dashboard.db import connect, init_db, insert_article_sql, row_to_dict
from news_dashboard.ingest.service import clean_html

logger = logging.getLogger(__name__)

_DEFAULT_FOLDER = "INBOX"
_DEFAULT_POLL_MINUTES = 15
_DEFAULT_MAX_MESSAGE_BYTES = 5 * 1024 * 1024
_SOURCE_CATEGORY = "newsletter"
_SOURCE_KIND = "newsletter"


class ImapClient(Protocol):
    """The subset of imaplib.IMAP4_SSL used by this module — for fake-client injection in tests."""

    def login(self, user: str, password: str) -> tuple[str, list[bytes]]: ...

    def select(self, mailbox: str) -> tuple[str, list[bytes | None]]: ...

    def search(self, charset: str | None, *criteria: str) -> tuple[str, list[bytes]]: ...

    def fetch(self, message_set: str, message_parts: str) -> tuple[str, list[Any]]: ...

    def store(self, message_set: str, command: str, flags: str) -> tuple[str, list[bytes]]: ...

    def logout(self) -> tuple[str, list[Any]]: ...


@dataclass(frozen=True)
class ImapConfig:
    host: str
    port: int
    username: str
    password: str
    folder: str = _DEFAULT_FOLDER


def imap_config() -> ImapConfig | None:
    """Return the configured IMAP mailbox, or None when the feature is inert.

    The feature requires host + username + password; port and folder have
    sane defaults so operators only need to set the mailbox credentials.
    """
    host = os.getenv("NEWSLETTER_IMAP_HOST", "").strip()
    username = os.getenv("NEWSLETTER_IMAP_USERNAME", "").strip()
    password = os.getenv("NEWSLETTER_IMAP_PASSWORD", "").strip()
    if not host or not username or not password:
        return None
    port = int(os.getenv("NEWSLETTER_IMAP_PORT", "993"))
    folder = os.getenv("NEWSLETTER_IMAP_FOLDER", _DEFAULT_FOLDER).strip() or _DEFAULT_FOLDER
    return ImapConfig(host=host, port=port, username=username, password=password, folder=folder)


def imap_configured() -> bool:
    """Return True when NEWSLETTER_IMAP_HOST/USERNAME/PASSWORD are all set."""
    return imap_config() is not None


def poll_minutes() -> int:
    return int(os.getenv("NEWSLETTER_POLL_MINUTES", str(_DEFAULT_POLL_MINUTES)))


def max_message_bytes() -> int:
    """Max accepted RFC822 message size before it's skipped without parsing. Default 5 MiB."""
    return int(os.getenv("NEWSLETTER_MAX_MESSAGE_BYTES", str(_DEFAULT_MAX_MESSAGE_BYTES)))


_PLUS_ADDRESS_RE = re.compile(r"^[^+@]+\+([^@]+)@", re.IGNORECASE)


def extract_plus_tag(addresses: list[str]) -> str | None:
    """Return the plus-address tag (e.g. 'alice' from 'inbox+alice@domain') or None.

    Scans all recipient addresses (To/Cc) since the plus-tagged address the
    newsletter was subscribed with may not be the first recipient.
    """
    for _name, addr in getaddresses(addresses):
        match = _PLUS_ADDRESS_RE.match(addr.strip())
        if match:
            return match.group(1).strip().lower()
    return None


def _user_id_for_username(conn: Any, username: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM users WHERE lower(username) = lower(%s)", (username,)
    ).fetchone()
    if row is None:
        return None
    return int(row_to_dict(row)["id"])


_SLUG_SANITIZE_RE = re.compile(r"[^a-z0-9]+")


def _sender_slug(owner_user_id: int, sender_name: str, sender_addr: str) -> str:
    """Derive a stable, per-owner source slug from the newsletter sender's domain/name.

    ``sources.slug`` is a global primary key (not scoped per-owner), so the
    slug must embed owner_user_id — otherwise two different users subscribing
    to the same newsletter sender would collide on one shared source row and
    the second user's articles would silently end up owned by the first.
    """
    domain = sender_addr.rsplit("@", maxsplit=1)[-1] if "@" in sender_addr else sender_addr
    base = sender_name.strip() or domain
    slug = _SLUG_SANITIZE_RE.sub("-", base.lower()).strip("-")
    if not slug:
        slug = _SLUG_SANITIZE_RE.sub("-", domain.lower()).strip("-") or "newsletter"
    return f"newsletter-{owner_user_id}-{slug}"[:120]


def _get_or_create_newsletter_source(
    conn: Any, *, owner_user_id: int, sender_name: str, sender_addr: str
) -> str:
    """Get or create a private newsletter-kind source owned by owner_user_id. Returns slug."""
    slug = _sender_slug(owner_user_id, sender_name, sender_addr)
    existing = conn.execute(
        "SELECT slug FROM sources WHERE slug = %s AND owner_user_id = %s",
        (slug, owner_user_id),
    ).fetchone()
    if existing is not None:
        return slug
    conn.execute(
        """
        INSERT INTO sources(slug, name, url, category, kind, priority, enabled, owner_user_id)
        VALUES (%s, %s, %s, %s, %s, 50, TRUE, %s)
        ON CONFLICT (slug) DO NOTHING
        """,
        (
            slug,
            sender_name or sender_addr,
            f"mailto:{sender_addr}",
            _SOURCE_CATEGORY,
            _SOURCE_KIND,
            owner_user_id,
        ),
    )
    return slug


def _decode_part(part: Message) -> str | None:
    """Return the decoded text payload of a message part, or None on failure."""
    try:
        payload = part.get_payload(decode=True)
    except Exception:
        logger.debug("Could not decode email part payload", exc_info=True)
        return None
    if not payload or not isinstance(payload, bytes):
        return None
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, ValueError):
        return payload.decode("utf-8", errors="replace")


def _iter_body_parts(message: Message) -> list[Message]:
    """Return the text/html and text/plain leaf parts of a message, in document order."""
    if not message.is_multipart():
        return [message]
    return [
        part
        for part in message.walk()
        if part.get_content_maintype() != "multipart" and not part.get_filename()
    ]


def _extract_body(message: Message) -> tuple[str, bool]:
    """Return (sanitized body text, is_html) from a parsed email message.

    Prefers the HTML part (sanitized via clean_html); falls back to the
    plain-text part when no HTML part is present.
    """
    html_part: str | None = None
    text_part: str | None = None
    for part in _iter_body_parts(message):
        content_type = part.get_content_type()
        if content_type == "text/html" and html_part is None:
            html_part = _decode_part(part)
        elif content_type == "text/plain" and text_part is None:
            text_part = _decode_part(part)

    if html_part is not None:
        return clean_html(html_part), True
    if text_part is not None:
        return text_part.strip(), False
    return "", False


def _published_date(message: Message) -> str | None:
    date_header = message.get("Date")
    if not date_header:
        return None
    try:
        return parsedate_to_datetime(date_header).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


def _message_id_url(message_id: str) -> str:
    """Wrap the RFC Message-ID as a stable pseudo-URL for the articles.url UNIQUE constraint."""
    return f"mid:{message_id.strip().strip('<>')}"


class NewsletterIngestError(RuntimeError):
    """Raised when a newsletter message could not be processed."""


def _process_message(conn: Any, raw_bytes: bytes) -> bool:
    """Parse and insert one newsletter email as an article. Returns True on success (or skip)."""
    message = message_from_bytes(raw_bytes)

    message_id = message.get("Message-ID")
    if not message_id:
        logger.warning("Newsletter message missing Message-ID header; skipping")
        return True  # not retryable — treat as handled so it doesn't loop forever

    recipients = message.get_all("To", []) + message.get_all("Cc", [])
    tag = extract_plus_tag(recipients)
    if tag is None:
        logger.warning(
            "Newsletter message %s has no plus-address tag in recipients; skipping", message_id
        )
        return True

    owner_user_id = _user_id_for_username(conn, tag)
    if owner_user_id is None:
        logger.warning(
            "Newsletter message %s addressed to unknown user %r; skipping", message_id, tag
        )
        return True

    from_header = message.get("From", "")
    sender_name, sender_addr = getaddresses([from_header])[0] if from_header else ("", "")
    if not sender_addr:
        logger.warning("Newsletter message %s missing From address; skipping", message_id)
        return True

    subject = str(message.get("Subject") or "Untitled").strip() or "Untitled"
    body, _is_html = _extract_body(message)
    published_at = _published_date(message)
    url = _message_id_url(message_id)

    source_slug = _get_or_create_newsletter_source(
        conn, owner_user_id=owner_user_id, sender_name=sender_name, sender_addr=sender_addr
    )
    source_row = conn.execute(
        "SELECT name, category FROM sources WHERE slug = %s", (source_slug,)
    ).fetchone()
    source = row_to_dict(source_row)

    summary = body[:280] + ("…" if len(body) > 280 else "")
    reason = f"Newsletter from {source['name']}."

    cursor = conn.execute(
        insert_article_sql(),
        (
            url,
            url,
            subject,
            source_slug,
            source["name"],
            source["category"],
            _SOURCE_KIND,
            published_at,
            summary,
            reason,
            50,
            "newsletter",
            None,
            body,
            "en",
        ),
    )
    if cursor.rowcount:
        logger.info(
            "Newsletter ingest: inserted article for user_id=%s source=%s subject=%r",
            owner_user_id,
            source_slug,
            subject,
        )
    else:
        logger.debug(
            "Newsletter ingest: message %s already ingested (dedup by Message-ID)", message_id
        )
    return True


def _connect_imap(config: ImapConfig) -> ImapClient:
    client = imaplib.IMAP4_SSL(config.host, config.port)
    client.login(config.username, config.password)
    return client  # structurally satisfies ImapClient; exact stub return types differ slightly


_RFC822_SIZE_RE = re.compile(rb"RFC822\s*\{(\d+)\}")


def _reported_message_size(fetch_header: Any) -> int | None:
    """Parse the IMAP-reported RFC822 literal size (e.g. ``1 (RFC822 {12345}``), or None."""
    if not isinstance(fetch_header, bytes):
        return None
    match = _RFC822_SIZE_RE.search(fetch_header)
    if match is None:
        return None
    return int(match.group(1))


def _fetch_raw_message(client: ImapClient, num_str: str) -> tuple[bytes, int | None]:
    """Fetch the raw RFC822 bytes of one message plus its IMAP-reported size, if known.

    Raises NewsletterIngestError on failure.
    """
    fetch_status, fetch_data = client.fetch(num_str, "(RFC822)")
    if fetch_status != "OK" or not fetch_data or not fetch_data[0]:
        msg = f"IMAP fetch failed for message {num_str}: {fetch_status}"
        raise NewsletterIngestError(msg)
    header, raw_bytes = fetch_data[0][0], fetch_data[0][1]
    return raw_bytes, _reported_message_size(header)


def poll_newsletters(
    db_path: Path | str | None = None,
    *,
    client_factory: Any = None,
) -> int:
    """Poll the configured IMAP mailbox for UNSEEN newsletter emails and ingest them.

    Returns the number of messages successfully processed (inserted or skipped
    for a known, non-retryable reason). Messages are marked \\Seen only after a
    successful insert attempt; on unexpected failure a message is left unread
    so the next poll retries it.

    ``client_factory`` allows tests to inject a fake IMAP client instead of
    connecting over the network; production code leaves it unset and a real
    ``imaplib.IMAP4_SSL`` connection is used.
    """
    config = imap_config()
    if config is None:
        logger.debug("Newsletter IMAP ingest skipped: not configured")
        return 0

    init_db(db_path)

    factory = client_factory or _connect_imap
    client: ImapClient = factory(config)
    processed = 0
    size_limit = max_message_bytes()
    try:
        client.select(config.folder)
        status, data = client.search(None, "UNSEEN")
        if status != "OK":
            msg = f"IMAP search failed: {status}"
            raise NewsletterIngestError(msg)
        message_numbers = data[0].split() if data and data[0] else []

        with connect(db_path) as conn:
            for num in message_numbers:
                num_str = num.decode() if isinstance(num, bytes) else str(num)
                try:
                    raw_bytes, reported_size = _fetch_raw_message(client, num_str)
                    actual_size = reported_size if reported_size is not None else len(raw_bytes)
                    if actual_size > size_limit:
                        logger.warning(
                            "Newsletter ingest: message %s is %d bytes (max %d); "
                            "skipping without parsing",
                            num_str,
                            actual_size,
                            size_limit,
                        )
                    else:
                        _process_message(conn, raw_bytes)
                    # Oversized messages are non-retryable: mark seen so the same
                    # message isn't re-fetched and re-rejected on every poll.
                    client.store(num_str, "+FLAGS", "\\Seen")
                    processed += 1
                except Exception:
                    logger.exception(
                        "Newsletter ingest: failed to process message %s; leaving unread", num_str
                    )
    finally:
        try:
            client.logout()
        except Exception:
            logger.debug("IMAP logout failed", exc_info=True)

    return processed
