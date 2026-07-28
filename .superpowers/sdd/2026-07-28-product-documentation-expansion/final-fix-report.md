# Final review fix report

## Status

Complete. The final review findings for issue #1285 are addressed in one
documentation-and-image fix wave.

Changed documentation:

- `website/docs/user-guide/application-tour.md` and
  `docs/user-guide/application-tour.md`
- `website/docs/user-guide/personalization-and-ai.md` and
  `docs/user-guide/personalization-and-ai.md`
- `website/docs/user-guide/recommendations.md` and
  `docs/user-guide/recommendations.md`
- `website/docs/getting-started/hosted-or-self-hosted.md`

Preserved and included image corrections:

- `website/static/img/user-guide/today-feed.webp`
- `website/static/img/user-guide/settings-personalization.webp`

## Claim sources

### Navigation and article-reader screenshot

- `frontend/src/lib/navigation.ts` defines Stats, Analytics, and Users in
  `adminNavigationItems` and only adds them for administrators.
- `frontend/src/AppRouter.tsx` guards Stats and Analytics with
  `AdminOnlyGuard`; `frontend/src/pages/AdminPage.tsx` rejects non-administrator
  access to Users.
- `frontend/src/components/article/ArticleActionBar.tsx` defines the reader's
  Star, Done, Later, Skip, and Archive actions shown in the corrected Today
  image.

The application tour now marks the administrator-only rail entries beside the
navigation image and identifies the Today image as the article reader reached
after opening an item.

### Reading DNA controls and role boundary

- `frontend/src/pages/ReadingDnaPage.tsx` renders the per-category and novelty
  sliders under Active nudges, sets their range to 0.0–3.0×, saves each change,
  and reports that changes save immediately.
- `backend/news_dashboard/user_settings/router.py` exposes authenticated
  per-user GET/PATCH recommendation preferences. The PATCH accepts only
  `category_weights` and `novelty_weight` and immediately calls
  `recompute_user_recommendations`.
- `backend/news_dashboard/recommendations.py` clamps both preference types to
  0–3, applies category weights directly, applies novelty only when an embedded
  taste profile exists, and keeps these settings in the reader's user settings.
- `backend/news_dashboard/recommendations_routes/router.py` provides the
  reader-owned manual refresh while keeping the instance-wide stale
  recalculation endpoint administrator-only.

The personalization guide now documents these reader-owned controls and limits
the instance role to background recalculation, stored-embedding availability,
and optional generated explanations.

### Current recommendation behavior

- `backend/news_dashboard/recommendations.py` defines Starred and Done as
  positive, Skip and Archive as negative, and Later as neutral. It also defines
  explicit thumbs feedback as a stronger separate signal.
- The same module verifies the active score inputs: cold-start metadata,
  per-user source/category/tag affinity, stored-embedding similarity,
  freshness, novelty, category preferences, and active learning goals.
- `backend/news_dashboard/ingest/service.py` orders Today candidates by stored
  personalized score with the cold-start score as the fallback.
- `frontend/src/lib/recommendation.ts` defines the Recommended, Relevant, and
  Low signal labels and factor-based fallback explanations.
- `frontend/src/components/article/ArticleWhyRecommended.tsx` exposes the Why
  recommended panel and adjacent thumbs feedback.
- `backend/news_dashboard/recommendations.py` confirms scoring itself needs no
  external provider, while configured providers can generate short
  explanations for the highest-ranked items.

The canonical guide and published mirror no longer describe Later as positive,
list dwell time as a scoring signal, claim multi-user collaborative filtering,
or present mix-ratio, minimum-age, or enable/disable controls. They document
only the current manual refresh, category-weight, and novelty controls.

### Read-only demo exception

- `backend/news_dashboard/demo.py` creates the bundled guest account as a
  read-only demo user.
- `website/docs/getting-started/try-the-demo.md` documents the rejected write
  operations.

The first workflow-equivalence claim in the hosted-versus-self-hosted guide now
limits equivalence to writable accounts and names the local demo exception
immediately.

## Screenshot inspection

Both images were inspected at original resolution:

| Image                           | Dimensions | Result                                                                                       |
| ------------------------------- | ---------- | -------------------------------------------------------------------------------------------- |
| `today-feed.webp`               | 1440×1000  | Reader action labels are readable; Star, Done, Later, Skip, and Archive are fully visible.   |
| `settings-personalization.webp` | 1065×690   | Theme, language, personalization, and AI Watchlists labels are inside the frame and legible. |

No username, email address, token, credential, notification endpoint, or other
account-specific value is visible in either image. Both files are valid RGB
WebP images.

## Verification

```text
npx prettier --check <seven changed guide Markdown files>
All matched files use Prettier code style.

node <normalized mirror and local-target validation>
mirror parity: 3/3; local link/image targets: 31/31

npm --prefix website run build
[SUCCESS] Generated static files in "build".

sips/file/shasum/wc checks
today-feed.webp: WebP, 1440x1000, 50,152 bytes
settings-personalization.webp: WebP, 1065x690, 18,682 bytes

git diff --check
Exit 0, no output.
```

Normalized parity strips Docusaurus front matter and maps repository image
paths to their `/img/user-guide/` published equivalents before comparison.
Local target validation resolves every relative guide link and image reference
in the changed published/mirror pages.

## Concerns

None.
