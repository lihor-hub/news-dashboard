# News Dashboard

News Dashboard is a self-hosted, open-source technical news reader that collects curated news from RSS/Atom feeds and other sources, supports triage, and generates AI briefings over the user's news corpus.

## Language

**Article**:
A news item discovered from a subscribed source.
_Avoid_: Feed item, story

**Workflow State**:
The user's triage position for an article, such as today, later, done, skipped, or archived. Workflow State does not decide whether an article belongs to the day's news corpus.
_Avoid_: Read status, started status

**Today Feed**:
The user's active triage queue for articles currently meant to be reviewed.
_Avoid_: Current-day news, all news

**Current-Day Report**:
A generated briefing that summarizes all news discovered in the current-day window from the user's available sources, regardless of Workflow State.
_Avoid_: Since-last-briefing report, Today-only briefing, inbox-only briefing

**Source Subscription**:
The set of news sources available to a user.
_Avoid_: Feed filter, source state
