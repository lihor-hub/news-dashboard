# The Today Feed & Triage States

The Today Feed is the heart of News Dashboard. It's your daily queue of
articles, and triage is how you process it.

## What is the Today Feed?

The Today Feed contains articles that are ready for you to review. Articles
enter the feed from:

- **New ingestion** — articles from your [Source Subscriptions](../concepts.md#source-subscription) discovered during the latest fetch.
- **Recommendations** — the app may surface older or related articles you haven't seen, based on your reading patterns.

The Today Feed is separated from your Later queue and your archive — it's
specifically the active batch you're working through *right now*.

## Triage states

Each article in your Today Feed can be moved to one of these states:

### Done
You've reviewed the article and moved on. Done articles are removed from the
Today Feed and stored in your read history. Use Done for articles you've read
fully or skimmed sufficiently.

### Later
Interesting, but you don't have time right now. Later articles are queued on
the Later page, where you can return to them when you're ready. The Later
queue is a separate triage surface — it doesn't mix back into Today.

### Skipped
Not relevant. Skipped articles are dismissed without being counted as read.
The app uses skip feedback to refine your recommendations.

### Starred
Saved as a permanent reference. Starred articles appear on the Starred page
and are immune to archival cleanup. Use the star for articles you want to
keep handy regardless of triage state.

### Snoozed
Hidden from the Today Feed until a time you choose. After the snooze period
expires, the article returns to Today. Useful for articles you want to read
but not right now — and don't want sitting indefinitely in Later.

### Archived
Tucked out of view. Archived articles don't appear in the Today Feed, Later,
or Done lists. You can restore an archived article to Done if you need it
back. Archiving is a way to declutter without permanently deleting.

## How triage works

Each article card shows:

- Title, source name, and discovery time
- A short summary (first ~280 characters of the body)
- A **reason** — a one-line contextual blurb explaining why this article surfaced ("New release v2.3.0 from source", "Trending on Hacker News", etc.)
- A **relevance** indicator when recommendations are active
- Triage action buttons: Done, Skip, Star, Later, Snooze

Triage actions happen immediately (optimistic updates). You can use keyboard
shortcuts on the Today Feed:

| Key | Action       |
| --- | ------------ |
| `d` | Mark Done    |
| `r` | Mark Done    |
| `s` | Star         |
| `l` | Send to Later|
| `x` | Skip         |
| `o` | Open article |
| `j` | Next article |
| `k` | Previous article |

After triaging an article, you're returned to your list automatically so you
can keep moving through the feed.

## Workflow State independence

A key concept: **Workflow State does not decide whether an article belongs to
the day's news corpus.** The [Current-Day Report](../briefings.md#the-current-day-report)
covers all articles discovered today, even ones you've already marked Done or
Skipped. This means your triage actions don't affect the briefing — the
briefing reflects what's happening, regardless of what you decided to read.
