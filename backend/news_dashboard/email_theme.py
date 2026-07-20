"""Shared visual identity and HTML primitives for transactional emails."""

from __future__ import annotations

import html
from collections.abc import Mapping
from typing import NamedTuple


class EmailColor(NamedTuple):
    """An email-safe color paired with its canonical application token."""

    css_variable: str
    app_token: str
    email_hex: str


EMAIL_COLORS: Mapping[str, EmailColor] = {
    "background": EmailColor("--background", "oklch(0.985 0.003 80)", "#faf8f5"),
    "foreground": EmailColor("--foreground", "oklch(0.2 0.012 70)", "#312e29"),
    "card": EmailColor("--card", "oklch(1 0 0)", "#ffffff"),
    "surface_muted": EmailColor("--surface-2", "oklch(0.945 0.006 80)", "#f1ede8"),
    "primary": EmailColor("--primary", "oklch(0.32 0.04 60)", "#594532"),
    "muted": EmailColor("--muted-foreground", "oklch(0.5 0.012 70)", "#77716a"),
    "accent": EmailColor("--accent", "oklch(0.55 0.13 45)", "#a95125"),
    "border": EmailColor("--border", "oklch(0.9 0.008 80)", "#e4ded7"),
}

FONT_SANS = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif"
FONT_SERIF = "'Source Serif 4', 'Iowan Old Style', Georgia, serif"
FONT_MONO = "'JetBrains Mono', 'SFMono-Regular', Consolas, monospace"


def _escape(value: str) -> str:
    """Escape email text using the entity spelling Jinja emits."""
    return html.escape(value, quote=True).replace("&#x27;", "&#39;")


def compact_text(value: object, *, fallback: str, limit: int = 120) -> str:
    """Normalize and bound user-facing text at the nearest word boundary."""
    normalized = " ".join(str(value).split()) if value else fallback
    if len(normalized) <= limit:
        return normalized

    prefix = normalized[: limit - 1].rstrip()
    if " " in prefix:
        word_boundary = prefix.rsplit(" ", 1)[0]
        if word_boundary:
            prefix = word_boundary
    return f"{prefix}…"


def render_email_shell(*, preheader: str, eyebrow: str, heading: str, body_html: str) -> str:
    """Wrap trusted message HTML in the shared News Dashboard email shell."""
    colors = EMAIL_COLORS
    safe_preheader = _escape(preheader)
    safe_eyebrow = _escape(eyebrow)
    safe_heading = _escape(heading)
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>{safe_heading}</title>
</head>
<body style="margin:0;padding:0;background:{colors["background"].email_hex};
             color:{colors["foreground"].email_hex};font-family:{FONT_SANS};">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">
    {safe_preheader}
  </div>
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
         style="width:100%;background:{colors["background"].email_hex};">
    <tr>
      <td align="center" style="padding:32px 16px;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
               style="width:100%;max-width:640px;">
          <tr>
            <td style="padding:0 4px 18px;">
              <table role="presentation" cellspacing="0" cellpadding="0">
                <tr>
                  <td style="width:34px;height:34px;border-radius:9px;
                             background:{colors["primary"].email_hex};color:#ffffff;
                             font-family:{FONT_SANS};font-size:12px;font-weight:700;
                             text-align:center;vertical-align:middle;">ND</td>
                  <td style="padding-left:11px;color:{colors["primary"].email_hex};
                             font-size:14px;font-weight:700;letter-spacing:.01em;">
                    News Dashboard
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="background:{colors["card"].email_hex};
                       border:1px solid {colors["border"].email_hex};border-radius:14px;
                       box-shadow:0 8px 28px rgba(49,46,41,.07);overflow:hidden;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                <tr>
                  <td style="padding:30px 32px 22px;border-bottom:1px solid
                             {colors["border"].email_hex};">
                    <p style="margin:0 0 8px;color:{colors["accent"].email_hex};
                              font-size:11px;font-weight:700;letter-spacing:.12em;
                              text-transform:uppercase;">{safe_eyebrow}</p>
                    <h1 style="margin:0;color:{colors["foreground"].email_hex};
                               font-size:25px;line-height:1.2;font-weight:700;
                               letter-spacing:-.02em;">{safe_heading}</h1>
                  </td>
                </tr>
                <tr>
                  <td style="padding:28px 32px;">{body_html}</td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:18px 12px 0;color:{colors["muted"].email_hex};
                       font-size:11px;line-height:1.55;text-align:center;">
              Sent by <strong style="color:{colors["primary"].email_hex};">
                News Dashboard
              </strong> &middot; Your personal news intelligence workspace
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def render_highlight_panel(*, label: str, value: str) -> str:
    """Render a warm highlighted value panel, escaping all caller content."""
    colors = EMAIL_COLORS
    safe_label = _escape(label)
    safe_value = _escape(value)
    return f"""
    <div style="margin:0 0 26px;padding:22px;text-align:center;
                background:{colors["surface_muted"].email_hex};
                border:2px solid {colors["accent"].email_hex};border-radius:10px;">
      <p style="margin:0 0 8px;color:{colors["accent"].email_hex};font-size:11px;
                font-weight:700;letter-spacing:.14em;text-transform:uppercase;">
        {safe_label}
      </p>
      <span style="display:inline-block;color:{colors["primary"].email_hex};
                   font-family:{FONT_MONO};font-size:38px;font-weight:700;
                   line-height:1;letter-spacing:.18em;">{safe_value}</span>
    </div>"""


def render_action_link(*, url: str, label: str) -> str:
    """Render the shared compact secondary action link."""
    safe_url = _escape(url)
    safe_label = _escape(label)
    return f"""<a href="{safe_url}"
      style="color:{EMAIL_COLORS["accent"].email_hex};font-size:12px;
             font-weight:600;text-decoration:none;">{safe_label} &rarr;</a>"""
