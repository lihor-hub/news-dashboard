#!/bin/sh
# Vercel ignoreCommand for both preview services: exit 0 skips the build,
# anything else builds. Both services share this list so a deployment never
# mixes a fresh frontend with a skipped backend (or the reverse). An unknown
# previous SHA (shallow clone, first deploy) makes git fail, so it builds.
exec git diff --quiet "${VERCEL_GIT_PREVIOUS_SHA:-HEAD^}" HEAD -- \
    frontend/ public/ index.html package.json package-lock.json \
    vite.config.ts 'tsconfig*.json' \
    scripts/check-bundle-budget.mjs scripts/check-csp-build.mjs \
    backend/news_dashboard/ pyproject.toml VERSION CHANGELOG.md \
    deploy/vercel/ vercel.json
