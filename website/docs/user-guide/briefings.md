---
title: Briefings
sidebar_position: 6
---

# Briefings

Briefings summarize the news discovered by your sources. The main briefing is
the **Current-Day Report**, a generated overview of today's articles.

## The Current-Day Report

The report answers: "What happened today in my subscribed sources?" It includes
all articles discovered during the current-day window, regardless of whether
you have already triaged them.

For each article, News Dashboard stores a short reason explaining why it
surfaced. Reasons are combined and ordered by importance so the report reads as
a compact daily overview.

## Delivery

Briefings can be read in the app. Depending on instance configuration, they can
also be delivered through in-app notifications, push notifications, email, or
generated podcast audio.

Audio features require a configured server-side text-to-speech path. OpenAI TTS
uses `OPENAI_API_KEY`; browser playback can use the device's built-in speech
synthesis for in-app listening.

## Privacy

Briefings are generated from your account's source subscriptions and stored in
the application database. Article content is sent to external providers only
when you configure the relevant AI or TTS provider credentials.
