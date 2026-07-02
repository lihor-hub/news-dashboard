---
title: Recommendations
sidebar_position: 7
---

# Recommendations

Recommendations surface articles that may be relevant based on your previous
triage behavior.

## How they work

News Dashboard scores candidate articles using local signals such as source,
category, tags, discovery time, and your past actions. Starring and marking
Done are positive signals; skipping is a negative signal; Later is a mild
positive signal.

Recommendations appear in the Today Feed with a relevance indicator and a short
"why recommended" explanation.

## Controls

Recommendation settings can control the mix ratio, minimum article age, and
whether recommendations are enabled at all. Turning recommendations off returns
the Today Feed to newly ingested articles only.

## Privacy

Recommendation scoring runs against your PostgreSQL data. No recommendation
query or behavior data needs to leave your instance.
