# Shared Email Visual Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give scheduled briefing, digest, and OTP messages one reusable News Dashboard email identity and prevent oversized article titles.

**Architecture:** A new `email_theme.py` module owns exact semantic app-token references, email-safe color/font values, compact-text behavior, and reusable HTML shell/components. Scheduled briefing, digest, and OTP modules supply escaped, message-specific content to that shared renderer. Contract tests bind CSS variable/value pairs and fonts to `frontend/src/globals.css`, while focused renderer tests cover shared identity, escaping, and title bounds.

**Tech Stack:** Python 3.14, standard-library HTML/email modules, pytest, Ruff, mypy, ty, pyrefly.

## Global Constraints

- The final displayed digest title never exceeds 120 characters and ends with one ellipsis when truncated.
- Digest HTML and plain text use the same normalized, bounded title.
- Dynamic titles, sources, summaries, and OTP codes are HTML-escaped.
- Existing SMTP, signed-link, delivery, ranking, recipient, and authentication behavior remains unchanged.
- Email HTML uses inline styles and presentation tables, without remote fonts, images, scripts, or CSS.
- The application CSS remains canonical; production email rendering must not read frontend files.

---

### Task 1: Shared Email Theme Foundation

**Files:**
- Create: `backend/news_dashboard/email_theme.py`
- Create: `backend/tests/test_email_theme.py`

**Interfaces:**
- Produces: `EMAIL_COLORS: Mapping[str, EmailColor]`, `FONT_SANS: str`, `FONT_SERIF: str`, `FONT_MONO: str`.
- Produces: `render_email_shell(*, preheader: str, eyebrow: str, heading: str, body_html: str) -> str`.
- Produces: `render_highlight_panel(*, label: str, value: str) -> str` and `render_action_link(*, url: str, label: str) -> str`.
- `body_html` is trusted HTML assembled by a renderer; all other string arguments are escaped inside the helper.

- [ ] **Step 1: Write failing shared-theme contract tests**

```python
from pathlib import Path

from news_dashboard import email_theme


def test_email_theme_references_canonical_application_tokens() -> None:
    css = Path("frontend/src/globals.css").read_text()
    for color in email_theme.EMAIL_COLORS.values():
        assert f"{color.app_token};" in css


def test_email_theme_uses_application_font_families() -> None:
    assert "Inter" in email_theme.FONT_SANS
    assert "Source Serif 4" in email_theme.FONT_SERIF
    assert "JetBrains Mono" in email_theme.FONT_MONO


def test_shell_escapes_text_and_includes_shared_identity() -> None:
    rendered = email_theme.render_email_shell(
        preheader="<preview>", eyebrow="News Dashboard", heading="Hello <reader>", body_html="<p>Safe body</p>"
    )
    assert "&lt;preview&gt;" in rendered
    assert "Hello &lt;reader&gt;" in rendered
    assert "<p>Safe body</p>" in rendered
    assert email_theme.EMAIL_COLORS["background"].email_hex in rendered
    assert email_theme.EMAIL_COLORS["primary"].email_hex in rendered
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `PATH="$PWD/.venv/bin:$PATH" dotenv run -- pytest backend/tests/test_email_theme.py -q`

Expected: collection fails because `news_dashboard.email_theme` does not exist.

- [ ] **Step 3: Implement the minimal shared theme**

Create an immutable `EmailColor` named tuple with `app_token` and `email_hex`, then define semantic colors whose `app_token` strings exactly match the light-theme OKLCH values in `frontend/src/globals.css`. Define the three email-safe font stacks. Implement a complete responsive presentation-table document in `render_email_shell`, and small reusable highlighted-panel/action-link helpers. Escape every helper text/URL argument using `html.escape(..., quote=True)`; interpolate `body_html` unchanged by its documented contract.

- [ ] **Step 4: Run shared-theme tests and verify GREEN**

Run: `PATH="$PWD/.venv/bin:$PATH" dotenv run -- pytest backend/tests/test_email_theme.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit the independently testable foundation**

```bash
git add backend/news_dashboard/email_theme.py backend/tests/test_email_theme.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat: add shared email visual identity (#1273)"
```

---

### Task 2: Digest Hierarchy and Bounded Titles

**Files:**
- Modify: `backend/news_dashboard/digest.py`
- Modify: `backend/tests/test_digest.py`

**Interfaces:**
- Consumes: `EMAIL_COLORS`, `FONT_SERIF`, `render_action_link`, and `render_email_shell` from `news_dashboard.email_theme`.
- Produces: `_display_title(value: object, *, limit: int = 120) -> str`.
- Preserves: `_render_html(articles: list[dict[str, Any]], *, user_id: int) -> str` and `_render_text(...) -> str`.

- [ ] **Step 1: Write failing digest behavior tests**

```python
def test_display_title_normalizes_and_truncates_at_word_boundary() -> None:
    title = "  " + "word " * 40
    rendered = digest._display_title(title)
    assert len(rendered) <= 120
    assert rendered.endswith("…")
    assert "  " not in rendered


def test_renderers_use_the_same_bounded_title() -> None:
    articles = [{**_ARTICLES[0], "title": "Headline " * 40}]
    expected = digest._display_title(articles[0]["title"])
    assert expected in digest._render_html(articles, user_id=7)
    assert expected in digest._render_text(articles, user_id=7)
    assert articles[0]["title"].strip() not in digest._render_html(articles, user_id=7)


def test_digest_uses_shared_warm_shell_and_small_action_link() -> None:
    rendered = digest._render_html(_ARTICLES, user_id=7)
    assert EMAIL_COLORS["background"].email_hex in rendered
    assert EMAIL_COLORS["primary"].email_hex in rendered
    assert "font-size:12px" in rendered
```

Extend the existing escaping test with a long title containing `<script>` near the truncation boundary and assert neither raw markup nor an over-120-character displayed title appears.

- [ ] **Step 2: Run focused digest tests and verify RED**

Run: `PATH="$PWD/.venv/bin:$PATH" dotenv run -- pytest backend/tests/test_digest.py -q -k 'display_title or bounded_title or shared_warm_shell or escapes_script'`

Expected: failures because `_display_title` and the shared digest shell are absent.

- [ ] **Step 3: Implement title bounding and migrate digest HTML**

Implement `_display_title` by converting a missing/false value to `"Untitled"`, collapsing whitespace with `" ".join(str(value).split())`, reserving one character for `…`, preferring `rsplit(" ", 1)[0]`, and falling back to a hard boundary. Call it before HTML escaping in `_render_html` and directly in `_render_text`. Replace the standalone HTML document with `render_email_shell`, render an intro count panel, warm-bordered article rows, serif summaries, compact metadata, and `render_action_link` for the signed mark-read URL.

- [ ] **Step 4: Run the entire digest test module and verify GREEN**

Run: `PATH="$PWD/.venv/bin:$PATH" dotenv run -- pytest backend/tests/test_digest.py -q`

Expected: all digest tests pass.

- [ ] **Step 5: Commit the digest change**

```bash
git add backend/news_dashboard/digest.py backend/tests/test_digest.py
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat: restyle digest email and bound titles (#1273)"
```

---

### Task 3: Scheduled Briefing and OTP Migration

**Files:**
- Modify: `backend/news_dashboard/briefing_email/rendering.py`
- Modify: `backend/news_dashboard/briefing_email/templates/briefing.html.j2`
- Test: `backend/tests/test_briefing_email_rendering.py`
- Modify: `backend/news_dashboard/email.py`
- Modify: `backend/tests/test_email.py`

**Interfaces:**
- Consumes: `EMAIL_COLORS`, `render_email_shell`, and `render_highlight_panel` from `news_dashboard.email_theme`.
- Scheduled briefing also consumes `compact_text`, `FONT_SERIF`, and `render_email_shell` while preserving Jinja autoescaping and safe-link filtering.
- Preserves: `send_otp_email(to_email: str, otp: str) -> None` and all SMTP configuration behavior.

- [ ] **Step 1: Write failing scheduled-briefing and OTP identity tests**

```python
def test_otp_email_uses_shared_warm_identity() -> None:
    msg = _capture_sent_message("user@example.com", "123456")
    html_body = _extract_html_body(msg)
    assert html_body is not None
    assert EMAIL_COLORS["background"].email_hex in html_body
    assert EMAIL_COLORS["primary"].email_hex in html_body
    assert "#2563eb" not in html_body


def test_otp_email_escapes_code() -> None:
    msg = _capture_sent_message("user@example.com", "<12345")
    html_body = _extract_html_body(msg)
    assert html_body is not None
    assert "<12345" not in html_body
    assert "&lt;12345" in html_body


def test_rendering_uses_shared_warm_email_identity() -> None:
    rendered = render_briefing_email(_briefing(), **_urls())
    assert EMAIL_COLORS["background"].email_hex in rendered.html_body
    assert EMAIL_COLORS["primary"].email_hex in rendered.html_body
    assert "#2563eb" not in rendered.html_body


def test_rendering_bounds_article_titles_in_html_and_text() -> None:
    briefing = _briefing()
    long_title = "An excessively detailed article title " * 12
    briefing["articles"][1]["title"] = long_title
    displayed = compact_text(long_title, fallback="Source")
    rendered = render_briefing_email(briefing, **_urls())
    assert displayed in rendered.html_body
    assert displayed in rendered.text_body
    assert long_title.strip() not in rendered.html_body
```

- [ ] **Step 2: Run focused email tests and verify RED**

Run: `PATH="$PWD/.venv/bin:$PATH" dotenv run -- pytest backend/tests/test_briefing_email_rendering.py backend/tests/test_email.py -q -k 'shared_warm_identity or shared_warm_email_identity or bounds_article_titles or escapes_code'`

Expected: scheduled-briefing and OTP identity/bounds assertions fail against the current blue templates.

- [ ] **Step 3: Migrate scheduled briefing and OTP content onto the shared shell**

Render the Jinja briefing template as a content fragment, bound cited-article titles with `compact_text`, and wrap it with `render_email_shell`; retain safe-link filtering, summary, story content, reading-time calculation, and footer links. Build only the OTP-specific explanatory copy and highlighted code panel in `email.py`. Use `render_highlight_panel` for the escaped code and `render_email_shell` for the document, retaining the current subject, expiry copy, safety guidance, MIME construction, SMTP branching, login, and send behavior.

- [ ] **Step 4: Run email-focused tests and verify GREEN**

Run: `PATH="$PWD/.venv/bin:$PATH" dotenv run -- pytest backend/tests/test_email_theme.py backend/tests/test_briefing_email_rendering.py backend/tests/test_email.py backend/tests/test_digest.py -q`

Expected: all focused tests pass.

- [ ] **Step 5: Inspect representative rendered messages**

Generate one scheduled briefing and one digest with overlong titles plus one OTP message through their pure render paths, save temporary HTML outside the repository, and inspect them at desktop and narrow widths. Confirm a warm cream shell, shared branded header/footer, bounded titles, readable intact summaries, compact links/actions, and escaped OTP panel. Do not commit temporary files.

- [ ] **Step 6: Run mandatory repository gates**

```bash
export PATH="$PWD/.venv/bin:$PATH"
export PGOPTIONS='-c max_parallel_workers_per_gather=0'
dotenv run -- make check
```

Expected: every command exits 0 with no lint/type errors or pytest failures.

- [ ] **Step 7: Commit final implementation and plan**

```bash
git add backend/news_dashboard/briefing_email backend/news_dashboard/email.py backend/tests/test_briefing_email_rendering.py backend/tests/test_email.py docs/superpowers/plans/2026-07-20-email-visual-identity.md
PATH="$PWD/.venv/bin:$PATH" git commit -m "feat: align scheduled emails with shared theme (#1273)"
```

- [ ] **Step 8: Review, rebase, publish, and merge**

Review `git diff origin/main...HEAD` against the specification and repository standards, repair confirmed findings, rerun affected gates, then execute:

```bash
git fetch origin
git rebase origin/main
git push -u origin HEAD
gh pr create --base main --title "feat: unify email visual identity" --body $'Closes #1273\n\n## Summary\n- add a reusable app-aligned email theme\n- migrate briefing, digest, and OTP emails to the shared identity\n- truncate normalized article titles to 120 characters\n\n## Testing\n- dotenv run -- make check\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)'
gh pr merge --squash --auto
gh pr checks --watch
```

Confirm the pull request is merged, issue #1273 is closed, and delete the remote feature branch if GitHub did not remove it.
