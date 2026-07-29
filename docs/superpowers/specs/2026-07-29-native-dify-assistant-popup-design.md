# Native Dify Assistant Popup

**Issue:** [#1296](https://github.com/lihor-hub/news-dashboard/issues/1296)

## Goal

Make the embedded Dify assistant feel like one News Dashboard surface without
reducing the popup's current usable area. The user should see one professional
product name, **News Assistant**, rather than an application wrapper title
stacked above Dify's own title.

## Constraints

- Dify runs in a sandboxed cross-origin iframe. News Dashboard cannot safely
  restyle or rename elements inside that document.
- The Dify application must therefore be named **News Assistant** in Dify's own
  application settings.
- The existing iframe dimensions, responsive placement, mobile behavior,
  sandbox permissions, disposable lifecycle, and privacy boundary remain
  unchanged.

## Design

### Popup frame

Remove the News Dashboard-owned header and its border separator. The Dify iframe
fills the existing dialog frame, reclaiming the header's vertical space without
changing the frame's width or height.

The outer frame continues to use News Dashboard's semantic background, border,
radius, and shadow tokens. This keeps the popup visually connected to the host
application in both light and dark themes while leaving Dify responsible for
the conversation surface inside the iframe.

### Close control

Keep one compact, icon-only News Dashboard close button over the upper-right
edge of the frame. Position it so it reads as frame chrome and does not obscure
Dify's internal refresh control. Its accessible name and tooltip remain
`Close News Assistant`, derived from the configured public title.

Escape closes the dialog while focus is in the parent document, and closing
restores focus to the launcher. These behaviors remain unchanged.

### Naming and configuration

The public `DIFY_TITLE` value remains the accessible dialog and launcher name.
Deployments should set it to `News Assistant`. The setup documentation will
also require the Dify application's display name to be `News Assistant`, since
that setting controls the title rendered inside the iframe.

No DOM injection, CSS injection, proxying, or same-origin relaxation will be
introduced to alter Dify's content.

## Testing

Follow red-green-refactor:

1. Add a component test asserting that an open popup has no host-owned visible
   heading while retaining the accessible dialog name and close control.
2. Assert that the iframe remains the direct full-size conversation surface and
   that the popup's established responsive sizing classes are preserved.
3. Keep the existing sandbox, lifecycle, URL privacy, Escape, and focus tests
   green.
4. Run the focused Vitest test, frontend formatting, ESLint, TypeScript, and
   production build gates.
5. Verify the popup visually in the running application at desktop and mobile
   viewport sizes.

## Out of Scope

- Changing Dify's conversation layout, colors, typography, messages, or
  branding from News Dashboard code.
- Reducing the popup dimensions.
- Passing News Dashboard user identity or briefing context into Dify.
- Changing the existing briefing-specific Q&A assistant.
