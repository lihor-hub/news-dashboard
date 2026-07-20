# Shared Email Visual Identity

## Context

The scheduled digest and one-time-password email currently look unrelated to
each other and to News Dashboard. Their blue and neutral styling conflicts with
the application's warm cream, charcoal, and coffee palette. Digest article
titles can also contain article-body-sized text, overwhelming the message.

## Goals

- Give every News Dashboard email one recognizable visual identity.
- Make that identity reusable by future transactional email templates.
- Align email colors and typography with the application's light theme while
  retaining email-client-safe fallbacks.
- Improve the digest's visual hierarchy and bound oversized article titles.
- Preserve SMTP configuration, delivery, authentication, signed links, article
  selection, summaries, and plain-text availability.

## Architecture

Add a backend email-theme module as the single rendering foundation for email.
It owns named palette and typography constants plus reusable helpers for the
document shell, branded header, content card, metadata, actions, highlighted
content, and footer. The digest and OTP renderers compose their content through
that foundation instead of defining independent visual systems.

The frontend remains the canonical application theme. A focused contract test
compares the email theme's semantic values and font families with the relevant
tokens in `frontend/src/globals.css`. This prevents accidental visual drift
without coupling production email rendering to frontend source files or adding
a cross-language asset-generation step.

Email HTML uses tables and inline styles for broad client compatibility. The
shared renderer escapes caller-provided text by default; URLs remain escaped at
their existing rendering boundary.

## Visual System

The light email identity maps to the application as follows:

- Page background: warm off-white/cream.
- Content surface: white with a warm muted border.
- Primary text and header: charcoal and deep coffee.
- Accent and links: the application's warm brown/orange accent family.
- Secondary text: muted warm gray.
- Sans typography: Inter first, then system and Arial fallbacks.
- Reading text: Source Serif 4 first, then Georgia and serif fallbacks where
  appropriate.
- Codes and numeric metadata: JetBrains Mono first, then standard monospace
  fallbacks.

The shell has a compact branded header, rounded content card, restrained shadow,
and shared footer. The OTP code appears in a warm highlighted panel rather than
a blue security panel. The digest begins with a compact count/intro treatment,
then presents articles as separated rows with title, source/score metadata,
summary, and a small action link.

## Digest Content Bounds

Article titles are normalized by collapsing whitespace. Titles longer than 120
characters are truncated at the last available word boundary and end with a
single ellipsis character. If no useful boundary exists, truncation occurs at
the character boundary. The final displayed title never exceeds 120 characters.
The same bounded title is used in HTML and plain-text digest representations so
one malformed feed entry cannot dominate either version.

Summaries remain intact and visually secondary. Article titles remain the
primary link to the source article. The signed “Mark as read” action is rendered
as smaller secondary link text.

## Safety and Compatibility

- Dynamic titles, sources, summaries, and codes remain HTML-escaped.
- Existing signed mark-read URLs and SMTP paths are unchanged.
- The OTP lifetime and security guidance remain unchanged.
- No remote web fonts, images, scripts, or CSS are required.
- Layout stays readable when rounded corners, shadows, or preferred fonts are
  unsupported.

## Testing

Development follows red-green-refactor:

1. Add failing focused tests for the shared theme, application-token alignment,
   both emails consuming the same shell, warm/non-blue styling, HTML escaping,
   and 120-character word-boundary truncation in HTML and text.
2. Implement the shared theme and migrate the digest and OTP renderers.
3. Run focused email tests, then backend lint, type checks, and the full Postgres
   test suite.
4. Inspect representative rendered HTML for hierarchy, spacing, long-title
   behavior, and narrow-width readability before opening the pull request.

## Out of Scope

- Dark-mode email variants.
- User-selectable email themes.
- Changes to delivery schedules, recipients, SMTP configuration, or digest
  ranking.
- A general-purpose templating dependency or frontend build-pipeline change.
