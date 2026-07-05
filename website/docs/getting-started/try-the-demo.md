# Try the Demo

The fastest way to see News Dashboard without setting up your own accounts,
sources, or AI keys is demo mode: a throwaway instance seeded with sample
articles and a read-only guest account.

## Run it

From a clone of the repository:

```bash
docker compose -f docker-compose.demo.yml up
```

This starts a bundled PostgreSQL instance and the published News Dashboard
image with `DEMO_MODE=1`. No `.env` file, API keys, or manual configuration
are required.

Open [http://localhost:8080](http://localhost:8080) and sign in with:

| Field    | Value   |
| -------- | ------- |
| Username | `guest` |
| Password | `demo`  |

## What's seeded

On first boot, demo mode seeds deterministic, fully offline sample data —
articles across categories like Python, AI/LLM, Rust, and cloud/infra, in a
mix of read, unread, saved, and archived states. No network requests or LLM
calls happen during seeding.

## Guest account limitations

The `guest` account is **read-only**. You can browse the Today Feed, search,
open articles, and explore the UI, but write actions (saving, marking read,
snoozing, adding sources, changing settings, and similar) are rejected.

## Next steps

Demo mode is for trying the app locally, not for a permanent or public
instance. When you're ready to run your own instance for real, see the
[Quick Start](https://github.com/lihor-hub/news-dashboard#quick-start) in the
README and the [Self-Hosting guide](/docs/self-hosting).
