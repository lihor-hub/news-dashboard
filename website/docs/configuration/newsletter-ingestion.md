---
title: Newsletter ingestion via IMAP
sidebar_position: 6
---

# Newsletter ingestion via IMAP

News Dashboard is a "news inbox", but a lot of technical writing ships as an
email-only newsletter (Substack and similar) with no RSS feed. Configuring an
IMAP mailbox lets those newsletters flow into the same triage/briefing/search
pipeline as every other source, as a private, per-user `newsletter`-kind
source.

This is a v1 feature: one shared mailbox, routed to users with
plus-addressing. It does not support per-user IMAP credentials, an inbound
SMTP server, attachment/image proxying, or OAuth IMAP.

## How it works

1. Every user gets their own plus-address on one shared mailbox:
   `inbox+<username>@yourdomain.example`.
2. The user subscribes a newsletter using that address instead of their real
   email.
3. A background job polls the mailbox for unread mail, maps the plus-address
   tag back to a username, and inserts each message as an article under a
   private source owned by that user (`kind="newsletter"`), invisible to
   everyone else.
4. HTML newsletters are sanitized into readable article bodies; plain-text-only
   messages still ingest, using the text part directly.
5. Re-polling the same message is a no-op — the RFC `Message-ID` header is used
   for idempotency, so a message is never turned into a duplicate article.
6. A message is marked read (`\Seen`) only once it's been successfully
   inserted; a message that fails to process is left unread so the next poll
   retries it.

## Setup

### 1. Create a mailbox

Set up a mailbox on any IMAP provider that supports plus-addressing (Gmail,
Fastmail, self-hosted Dovecot/Postfix, etc.) — for example
`inbox@yourdomain.example`. Note the IMAP host/port and a username/password
(or app password) News Dashboard can log in with.

### 2. Configure the environment

Set the following on the backend:

```bash
NEWSLETTER_IMAP_HOST=imap.yourdomain.example
NEWSLETTER_IMAP_PORT=993
NEWSLETTER_IMAP_USERNAME=inbox@yourdomain.example
NEWSLETTER_IMAP_PASSWORD=your-app-password
# Optional, defaults shown:
NEWSLETTER_IMAP_FOLDER=INBOX
NEWSLETTER_POLL_MINUTES=15
```

The feature is fully inert — no background job is scheduled and no mailbox is
ever contacted — unless `NEWSLETTER_IMAP_HOST`, `NEWSLETTER_IMAP_USERNAME`,
and `NEWSLETTER_IMAP_PASSWORD` are all set.

### 3. Give each user their plus-address

Each user subscribes newsletters using `inbox+<their-username>@yourdomain.example`,
where `<their-username>` is their News Dashboard login username. For example, a
user named `alice` would use `inbox+alice@yourdomain.example` when signing up
for a Substack newsletter.

Mail addressed to a plus-tag that doesn't match any username, or with no
plus-tag at all, is skipped and logged rather than guessed at.

### 4. Subscribe newsletters

Go to the newsletter's subscription page (Substack, etc.) and use the
plus-address from step 3 as the subscriber email. New issues will show up as
articles the next time the poll job runs (`NEWSLETTER_POLL_MINUTES`, default
every 15 minutes), under a private source named after the sender.
