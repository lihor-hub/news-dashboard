"""Contract tests for the shared transactional-email visual identity."""

from pathlib import Path

from news_dashboard import email_theme


def test_email_theme_references_canonical_application_tokens() -> None:
    css = Path("frontend/src/globals.css").read_text()

    for color in email_theme.EMAIL_COLORS.values():
        assert f"{color.css_variable}: {color.app_token};" in css


def test_email_theme_uses_application_font_families() -> None:
    css = Path("frontend/src/globals.css").read_text()

    assert "Inter" in email_theme.FONT_SANS
    assert "Source Serif 4" in email_theme.FONT_SERIF
    assert "JetBrains Mono" in email_theme.FONT_MONO
    assert "--font-sans: 'Inter Variable'" in css
    assert "--font-serif: 'Source Serif 4 Variable'" in css
    assert "--font-mono: 'JetBrains Mono Variable'" in css


def test_shell_escapes_text_and_includes_shared_identity() -> None:
    rendered = email_theme.render_email_shell(
        preheader="<preview>",
        eyebrow="News Dashboard",
        heading="Hello <reader>",
        body_html="<p>Safe body</p>",
    )

    assert "&lt;preview&gt;" in rendered
    assert "Hello &lt;reader&gt;" in rendered
    assert "<p>Safe body</p>" in rendered
    assert email_theme.EMAIL_COLORS["background"].email_hex in rendered
    assert email_theme.EMAIL_COLORS["primary"].email_hex in rendered


def test_highlight_panel_and_action_link_escape_dynamic_values() -> None:
    panel = email_theme.render_highlight_panel(label="Code <now>", value="<12345")
    link = email_theme.render_action_link(
        url='https://example.com/?value="unsafe"',
        label="Open <article>",
    )

    assert "Code &lt;now&gt;" in panel
    assert "&lt;12345" in panel
    assert "value=&quot;unsafe&quot;" in link
    assert "Open &lt;article&gt;" in link


def test_compact_text_normalizes_and_truncates_at_word_boundary() -> None:
    rendered = email_theme.compact_text("  " + "article title " * 20, fallback="Source")

    assert len(rendered) <= 120
    assert rendered.endswith("…")
    assert "  " not in rendered
    assert rendered.removesuffix("…").endswith("title")
