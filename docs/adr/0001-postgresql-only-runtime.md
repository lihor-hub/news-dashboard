# PostgreSQL-Only Runtime Database

- Status: accepted
- Deciders: ioachim-hub, Antigravity
- Date: 2026-06-30

Technical Story: [Issue #633](https://github.com/lihor-hub/news-dashboard/issues/633), [docs/ARCHITECTURE.md](../ARCHITECTURE.md)

## Context and Problem Statement

To minimize application complexity and leverage PostgreSQL's advanced capabilities (such as UPSERTs via `ON CONFLICT`, native JSON/array operators, and fast batch inserts), we need a clear database contract. Allowing multiple SQL dialects (like supporting SQLite for local runs and PostgreSQL for production) would require adding database-type sniffing, translation layers, or ORM overhead, which increases maintenance and bugs.

## Decision Drivers

- Maintain code simplicity (raw PostgreSQL-specific SQL queries with `psycopg`).
- Minimize testing surface (avoid testing all database interactions on both SQLite and PostgreSQL).
- Fully exploit PostgreSQL performance and features.

## Considered Options

- **Option 1: PostgreSQL-only runtime**: Enforce PostgreSQL as the exclusive database for local development, CI/CD, and production deployments.
- **Option 2: Multi-database support (PostgreSQL + SQLite)**: Build a translation layer or use an ORM to support both SQLite (for easy local setup) and PostgreSQL (for production).

## Decision Outcome

Chosen option: **Option 1: PostgreSQL-only runtime**, because it keeps the application code highly optimized, simple, and predictable. SQLite is strictly prohibited at runtime.

### Consequences

- **Good (Pros)**:
  - No multi-dialect database translation layer or ORM overhead is needed.
  - Direct use of robust, database-specific features like `ON CONFLICT` is encouraged.
  - Local development matches production behavior exactly (reducing "works on my machine" issues).
- **Bad (Cons)**:
  - Running the application locally requires a PostgreSQL instance (mitigated by Docker Compose and VS Code Dev Container configurations).
- **Neutral/Other**:
  - SQLite is allowed only in legacy import/migration tools (`news-dashboard-migrate`) which ingest old SQLite data files and write them into PostgreSQL.
