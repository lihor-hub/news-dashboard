# Recommendations

Discover articles you might have missed with **Recommendations** — personalized
suggestions that learn from your triage behavior to surface relevant, older, or
related content in your Today Feed.

## How recommendations work

News Dashboard watches how you triage articles (Done, Skip, Star, etc.) and
uses those signals to score unseen articles in your database. Articles with
high scores appear in your Today Feed with a **"Why recommended"** explanation
and a relevance indicator.

The recommender does **not** look at article content or use external services.
It operates purely on:
- Your past actions (which articles you did/didn't engage with)
- Article metadata (source, category, tags, discovery time)
- Simple collaborative filtering (users with similar behavior patterns)

No machine learning models, no external APIs, no data leaves your instance.

## Where you see recommendations

Recommendations appear mixed into your **Today Feed** alongside new
ingestions. Recommended articles are marked with:

1. **A relevance badge** — a colored dot indicating how strongly the article
   matches your interests (calculated from your history)
2. **A "Why recommended" button** — tap to see a short explanation like:
   - "You often star articles from this source"
   - "You read similar articles about this topic"
   - "This matches your saved article patterns"
   - "You skipped fewer articles from this category recently"

## Training the recommender

The system learns implicitly from your normal usage — no explicit training
required. Signals that strengthen recommendations:

- **Starring** an article → strong positive signal
- **Marking Done** → positive signal (you found it worth reading)
- **Skipping** an article → negative signal (less relevant to you)
- **Saving to Later** → mild positive signal (interested but not now)
- **Time spent** (if available) — longer reads suggest higher interest

The recommender adapts continuously. If you start skipping articles you used
to star, the weights shift and those topics appear less frequently.

## Recommendations in the Today Feed

When recommendations are active:
- Your Today Feed blends **new articles** (from the latest ingest) with
  **recommended articles** (from your existing database)
- The mix aims to balance freshness with relevance
- You can tell an article is recommended by the presence of:
  - The relevance indicator (dot or bar)
  - The "Why recommended" button (tapping shows the explanation)
- Recommended articles still follow normal triage — you can Done, Skip,
  Star, etc. them just like new articles

## Controlling recommendations

You can adjust recommendation behavior in Settings → Recommendations:

- **Mix ratio** — what percentage of your Today Feed should be recommendations
  (default: 30%, range: 0%–100%)
- **Minimum age** — how old an article must be to be considered for
  recommendation (default: 2 days, prevents brand-new items from being
  labeled as "recommended")
- **Feature toggle** — turn recommendations off entirely to see only new
  ingestions in your Today Feed

## Where recommendations pull from

The recommender scans your entire article database (excluding items you've
already interacted with in the current session) to find:
- Articles you haven't seen yet (status: `new`)
- Articles you previously skipped but might now find relevant
- Older saved/articles you haven't read
- Items from sources/categories you engage with frequently

It does **not** recommend:
- Articles you've already triaged (Done/Skipped/Starred) in this session
- Archived items (unless restored)
- Items from disabled sources

## Privacy

Recommendations are 100% local and private:
- No user behavior leaves your server
- No external model calls or API keys needed
- No collaborative filtering with other users (the "similar users" pattern
  is computed entirely from your local data)
- All scoring happens in-memory using your PostgreSQL data
