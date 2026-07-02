---
title: Sharing articles
sidebar_position: 9
---

# Sharing articles

Sharing lets you send an article to another user on the same News Dashboard
instance without exposing your personal triage state.

## How sharing works

The app creates a time-limited token and a share record that links sender,
recipient, and article. When the recipient opens the share, the token is
validated, the article opens in their account, and their own triage actions are
recorded separately.

The recipient can see the article and shared note, but not your private state,
read timestamps, or personal notes.

## Requirements

Sharing requires both users to have accounts on the same instance. No external
service is needed.

Shares are single-use, expire automatically, and can be revoked before they are
opened.
