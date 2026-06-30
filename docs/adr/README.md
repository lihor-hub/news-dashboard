# Architecture Decision Records (ADRs)

This directory contains records of significant architectural decisions made for the news-dashboard project. We use these records to document the context, alternatives considered, chosen solutions, and consequences of these choices to maintain a clear history for developers and maintainers.

## What is an ADR?

An Architecture Decision Record (ADR) is a document that captures a point-in-time decision about the system's design or infrastructure. Each decision is numbered sequentially and follows a consistent template.

## Creating a New ADR

1. Copy the [0000-template.md](0000-template.md) to a new file named `XXXX-[short-description].md` where `XXXX` is the next sequential 4-digit number.
2. Fill in the template fields (Status, Deciders, Context, Drivers, Options, and Consequences).
3. Update this index file (`README.md`) to list the new ADR.
4. Open a pull request containing the new ADR.

## ADR Index

| ADR ID                                  | Decision Title                              | Status   | Date       |
| --------------------------------------- | ------------------------------------------- | -------- | ---------- |
| [0001](0001-postgresql-only-runtime.md) | PostgreSQL-Only Runtime Database            | Accepted | 2026-06-30 |
| [0002](0002-llm-gateway-fallback.md)    | Free-LLM Gateway first with OpenAI Fallback | Accepted | 2026-06-30 |

_Template: [0000-template.md](0000-template.md)_
