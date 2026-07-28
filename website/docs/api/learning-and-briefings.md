---
title: Learning and briefings
sidebar_position: 5
---

# Learning and briefings

Everything in this section is **generated** rather than fetched. These routes
call an LLM, cost real time and money per request, and are the slowest part of
the API. Treat them as asynchronous work, not as reads.

## Briefings

A briefing is a periodic digest assembled from your recent articles.

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/briefings` | GET | List briefings. |
| `/api/briefings` | POST | Generate a briefing now. |
| `/api/briefings/latest` | GET | The most recent briefing. |
| `/api/briefings/{briefing_id}` | GET | One briefing. |
| `/api/briefings/{briefing_id}/chat` | POST | Ask follow-up questions about it. |

### Briefing podcasts

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/briefings/{briefing_id}/podcast` | POST | Generate audio for a briefing. |
| `/api/briefings/{briefing_id}/podcast` | GET | Generation status / result. |

`POST` starts generation; `GET` reports where it got to. Poll the `GET` rather
than assuming the `POST` response is final.

Two routes are public because podcast players cannot authenticate:

| Route | Access |
|-------|--------|
| `/api/briefings/podcast.rss` | Token in the URL. The subscribable feed. |
| `/api/briefings/{briefing_id}/podcast-audio` | Token in the URL. The audio file. |

Token management is covered in
[Authentication → Podcast feed tokens](authentication.md#podcast-feed-tokens).

### Email delivery and unsubscribe

Briefings can be emailed. The unsubscribe endpoints are public by necessity —
an unsubscribe link in an email must work without a login:

| Route | Method |
|-------|--------|
| `/email/briefing/unsubscribe` | GET |
| `/email/briefing/unsubscribe` | POST |

The `GET` renders a confirmation page; the `POST` performs the opt-out. Email
clients pre-fetch links, so a one-click `GET` that unsubscribed directly would
opt users out by accident.

## Lessons

Lessons turn a link or topic into structured learning material.

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/learn/lessons` | GET | List lessons. |
| `/api/learn/lessons` | POST | Create a lesson from a link or topic. |
| `/api/learn/lessons/{lesson_id}` | GET | One lesson. |
| `/api/learn/lessons/{lesson_id}/regenerate` | POST | Regenerate content. |
| `/api/learn/lessons/{lesson_id}/generations` | GET | Generation history. |
| `/api/learn/lessons/{lesson_id}/trails` | GET | Suggested follow-on paths. |
| `/api/learn/lessons/{lesson_id}/questions` | POST | Generate questions. |

### Alternate renderings

The same lesson can be rendered into other media:

| Route | Method | Produces |
|-------|--------|----------|
| `/api/learn/lessons/{lesson_id}/podcast` | POST / GET | Audio. |
| `/api/learn/lessons/{lesson_id}/slides` | POST | A slide deck. |
| `/api/learn/lessons/{lesson_id}/infographic` | POST | An infographic. |

`/generations` exists because these are non-deterministic: it records what was
produced and when, so a regeneration does not silently discard prior output.

### Suggestions

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/learn/suggestions` | GET | Suggested lessons based on your reading. |
| `/api/learn/suggestions/dismiss` | POST | Dismiss a suggestion. |
| `/api/learn/lessons/{lesson_id}/relevance/feedback` | POST | Report whether a lesson was relevant. |

Feedback here feeds ranking — it is the signal that stops the same unwanted
suggestion from recurring.

## Goals and quizzes

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/goals` | GET | List reading goals. |
| `/api/goals` | POST | Create a goal. |
| `/api/goals/{goal_id}` | DELETE | Delete a goal. |
| `/api/quizzes` | GET | List quizzes. |
| `/api/quizzes/latest` | GET | Most recent quiz. |
| `/api/quizzes/candidates` | GET | Articles eligible for a quiz. |
| `/api/quizzes/generate` | POST | Generate a quiz. |
| `/api/quizzes/{quiz_id}/submit` | POST | Submit answers. |

Check `/api/quizzes/candidates` before generating — quiz quality depends on
having enough recently-read material, and this reports whether there is.

## Recaps

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/recaps` | GET | List periodic recaps. |
| `/api/recaps/latest` | GET | Most recent recap. |
| `/api/lesson-recaps` | GET | List lesson recaps. |
| `/api/lesson-recaps/latest` | GET | Most recent lesson recap. |
| `/api/lesson-recaps/generate` | POST | Generate one now. |
| `/api/lesson-recaps/{recap_id}/podcast` | POST / GET | Audio for a lesson recap. |

## Assistant and agent actions

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/ask` | POST | Ask a question across your articles. |
| `/api/summary` | GET | A generated summary view. |
| `/api/feedback` | POST | Feedback on a generated answer. |

Agent actions are multi-step operations that run under explicit approval:

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/agent/actions/plan` | POST | Produce a plan without executing it. |
| `/api/agent/actions/{run_id}` | GET | Inspect a run. |
| `/api/agent/actions/{run_id}/approve` | POST | Approve and execute. |
| `/api/agent/actions/{run_id}/cancel` | POST | Cancel. |

Planning and execution are deliberately separate calls. The agent never
performs a mutating action without an explicit `approve`.

## Personalization

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/personalization/nudges` | GET | Suggested adjustments to your setup. |
| `/api/personalization/nudges/apply` | POST | Apply a nudge. |
| `/api/personalization/nudges/dismiss` | POST | Dismiss it. |
| `/api/users/me/recommendation-preferences` | GET / PATCH | Tune recommendations. |

### AI memory

Durable, user-editable facts the assistant may use as context:

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/users/me/ai-memories` | GET | List memories. |
| `/api/users/me/ai-memories` | POST | Add one. |
| `/api/users/me/ai-memories/{memory_id}` | PATCH | Edit one. |
| `/api/users/me/ai-memories/{memory_id}` | DELETE | Delete one. |
| `/api/users/me/ai-memories/learn-from-reading` | POST | Derive memories from reading history. |

Memories are inspectable and deletable by design — the assistant should never
hold context about a user that the user cannot see or remove.

### Feedback on AI output

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/ai-feedback` | GET / POST / DELETE | Record or withdraw feedback on generated output. |

## Onboarding

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/onboarding/status` | GET | Where the user is in onboarding. |
| `/api/onboarding/interests` | GET / POST | Read or set interests. |
| `/api/onboarding/recommendations` | POST | Recommendations from interests. |
| `/api/onboarding/source-recommendations` | GET | Suggested sources to subscribe to. |
| `/api/onboarding/profile` | POST | Save the onboarding profile. |
