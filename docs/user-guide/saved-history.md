# Saved & Read History

Your personal article archive — the articles you've **Saved**, **Read**, or
**Starred** — is searchable, browsable, and powers features like
Recommendations and the Reading DNA.

## What counts as "read" or "saved"?

News Dashboard tracks user interaction with articles:

- **Read** — you've opened and viewed the article (marked Done)
- **Saved** — you've explicitly set aside for later (Saved state, not to be
  confused with the verb "to save")
- **Starred** — you've marked as a permanent reference (immune to archival)
- **Snoozed** — temporarily hidden until a future time

Each of these actions stores a timestamp (`read_at`, `saved_at`, `starred_at`,
`snoozed_at`, `unsnoozed_at`) so you can see when you interacted with an
article.

## Where to find your history

Navigate to these tabs to browse your personal archive:

| Tab         | Contains                                                                  |
| ----------- | ------------------------------------------------------------------------- |
| **Read**    | Articles you've marked Done                                               |
| **Saved**   | Articles you've set to Later (the "read-it-later" queue)                  |
| **Starred** | Articles you've Starred (your permanent reference library)                |
| **Archived**| Articles you've tucked away (can be restored to Read)                     |

Each tab shows:
- Article title, source, and discovery time
- Your interaction timestamp (when you read/saved/etc.)
- Tags (if you've applied any)
- A shortcut to triage the article again (e.g., from Saved to Read)

## Search within history

You can search your Saved, Read, or Starred tabs just like the Today Feed:
- Open the tab
- Focus the search box (click the magnifying glass or press `/`)
- Type your query — results are limited to articles in that tab

This lets you quickly find, for example:
- "all Saved articles about Kubernetes"
- "Starred Python releases from June"
- "Read articles where I skipped the AI summary"

## The Reading DNA

The **Reading DNA** is a personalized snapshot of your reading habits,
accessible from your user menu. It shows:

- **Articles read** — total count and trend over time
- **Reading time saved** — estimated hours saved via summaries vs. full reads
- **Top categories** — which source categories you engage with most
- **Top sources** — individual feeds you read most frequently
- **Top tags** — keywords you've applied to articles
- **Streaks** — consecutive days with reading activity (if streaks feature is enabled)
- **Recent activity** — your last few interactions (article + timestamp)

The Reading DNA updates in real time as you triage and read articles. It's a
private dashboard — only you can see your own DNA on a multi-user instance.

## Tags and history

If you use the **tags** feature (user-defined labels), your tags appear in:
- Article cards across all tabs
- The Reading DNA (top tags list)
- Search results (you can search by tag)
- The tag management view (where you can rename or delete tags)

Tags are a powerful way to organize your Saved and Read history beyond
categories and sources.

## Exporting your data

Want to back up or migrate your history? Use the built-in export:

1. Go to Settings → Advanced
2. Click "Download archive"
3. Receive a JSON file containing:
   - Export metadata (`schema_version`, `generated_at`, and
     `includes_article_bodies`, which is currently `false`)
   - Your article interactions (read/saved/starred/etc. timestamps),
     article metadata, summaries, source information, and workflow state
   - Applied tags
   - Briefings history, with cited article IDs
   - `source_subscriptions` — your enabled/disabled state for global sources,
     plus any private sources you own (other users' private sources are
     never included)
   - `preferences` — recommendation weights, onboarding
     interests/completion state, and notification settings (briefing
     time/timezone, push-enabled, recap, analytics opt-in)

The export does not include cached article body text. Secrets (password hash,
session tokens, push subscription keys, API tokens) are never included.

To restore an archive, click "Restore archive" next to the download button
and pick a previously downloaded JSON file. Re-importing the same file is
safe: existing articles, briefings, and AI memories are matched and updated
in place rather than duplicated. Only the same major archive schema version
produced by this instance can be restored (an older or newer
`schema_version` is rejected), and restoring only ever writes data for your
own account.

## Auto-cleanup

To keep your database lean, News Dashboard automatically removes certain
interactions after a period:

- **Read/Done articles** — kept indefinitely (they form your reading history)
- **Saved/Later articles** — kept until you change their state
- **Starred articles** — kept indefinitely (permanent reference)
- **Snoozed articles** — automatically unsnoozed when the timer expires
- **Article views** — no separate view logs are stored (privacy by design)

The `user_events` table (used for analytics and streaks) is pruned according
to `ANALYTICS_RETENTION_DAYS` (default: 180 days) by a daily cleanup job.

## Privacy

Your Saved and Read history is:
- 100% local — stored only in your PostgreSQL database
- Never sent externally unless you explicitly export it
- Not used for advertising or profiling
- Accessible only to your user account (on multi-user instances)
