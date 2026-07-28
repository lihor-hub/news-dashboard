# Product Documentation Expansion Design

**Issue:** [#1285](https://github.com/lihor-hub/news-dashboard/issues/1285)
**Status:** Approved for planning
**Date:** 2026-07-28

## Problem

The latest hosted release exposes more user-facing capabilities than the
published documentation makes discoverable. The user-guide index currently
centers on the core reading workflow, while the application also includes AI
watchlists and memory, learning workflows, collections, recaps, offline access,
statistics, administration, and operational feed views. Existing MCP and Google
Reader-compatible integration guides are also absent from the Configuration
index.

The documentation does not consistently explain whether a task is performed by
an end user on the official hosted service or by an operator configuring a
self-hosted deployment.

## Readers and Tasks

The documentation serves three readers:

1. A reader using the official hosted service who needs to create an account,
   navigate the application, personalize it, and understand which settings they
   control.
2. A self-hoster who needs to deploy the platform, enable optional
   integrations, and understand how deployment configuration affects the UI.
3. An instance administrator who needs to manage users, sources, schedules,
   ingestion runs, logs, and analytics.

Each guide begins with the task the reader can complete and labels the required
role and deployment availability near the relevant step.

## Source of Truth

Documentation claims are verified against:

- the authenticated official hosted application at `https://news.lihor.ro`;
- current frontend routes, page components, and API clients;
- current backend settings, routers, services, and environment-variable use;
- Docker Compose, Helm, and example environment configuration;
- existing published and mirrored documentation.

The hosted UI is the visual source of truth. Source code and deployment
configuration are authoritative for feature gates, permissions, and self-hosted
configuration.

## Information Architecture

### Getting started

Add a hosted-versus-self-hosted guide that explains:

- how to choose between the official hosted service, local demo, and a
  self-hosted deployment;
- who creates accounts and who controls server configuration;
- which tasks are available to readers, administrators, and deployment
  operators;
- where to continue for the first useful workflow.

### User guide

Add task-oriented guides rather than one page per route:

- **Application tour:** primary navigation, the More menu, the Brief, Today,
  article reading, search, and the relationship between core destinations.
- **Personalization and AI:** recommendations, Ask, AI Watchlists, AI Memory,
  Topic Map, and AI Stats, including optional service requirements.
- **Organize and learn:** Later, Starred, Reading List, Collections, Learn,
  Lesson Library, Learning Recap, Weekly Recap, and Offline Saved.
- **Settings and account data:** theme, language, recommendation refresh,
  briefing schedule, delivery, privacy, export/restore, updates, and account
  deletion.

Existing focused pages remain canonical for detailed workflows such as
briefings, search, sharing, sources, recommendations, and the knowledge graph.
New overview pages link to them instead of duplicating their content.

All published user-guide changes under `website/docs/user-guide/` are mirrored
under `docs/user-guide/`.

### Administration and configuration

Add an administrator and operations guide covering user administration, feed
management, scheduling, run history, logs, statistics, and analytics. It
distinguishes application-admin controls from deployment-operator
configuration.

Update the Configuration index to surface the existing MCP server and Google
Reader-compatible sync guides, plus any current integration guide omitted by
the audit.

Self-hosted instructions point to exact environment variables and existing
deployment guides. They do not duplicate the full environment-variable
reference.

## Screenshots

Capture privacy-safe screenshots from the official hosted release for:

- the generated Brief;
- the Today feed and triage controls;
- the navigation menu or application tour;
- the learning or organization workflow;
- settings sections that contain no personal address, token, or secret;
- an administration or operations surface when it contains no sensitive user
  data.

Screenshots use a consistent desktop viewport, WebP output, descriptive
filenames, and concise alt text. Crop or omit any surface that exposes email
addresses, usernames, tokens, source credentials, internal identifiers, or
private account data. Screenshots supplement instructions; no required step is
communicated only through an image.

## Scope Control

This change updates documentation and documentation image assets only. It does
not change application behavior, add new features, alter deployment defaults,
or expose optional integrations on the hosted service.

An audited feature may be deferred when it is experimental, unavailable in the
current hosted release, unsafe to illustrate, or lacks a stable user workflow.
Any deferral is recorded in the implementation notes rather than silently
omitted.

## Verification

Before delivery:

1. Compare every new claim with the hosted UI or a current source/configuration
   path.
2. Verify `docs/user-guide/` and `website/docs/user-guide/` mirror parity for
   changed pages.
3. Build the documentation website with its repository-native command.
4. Check new internal links and navigation entries.
5. Inspect every screenshot for legibility and private information.
6. Review the complete diff for duplication, stale terminology, and accidental
   product claims.

## Completion

The work is complete when the new guides and screenshots are merged, the
published documentation navigation exposes them, CI passes, and issue #1285 is
closed by the pull request.
