# Free-LLM Gateway First with OpenAI Fallback

- Status: accepted
- Deciders: ioachim-hub, Antigravity
- Date: 2026-06-30

Technical Story: [Issue #633](https://github.com/lihor-hub/news-dashboard/issues/633), [ai_client.py](../../backend/news_dashboard/ai_client.py)

## Context and Problem Statement

Ingestion processes, text-to-speech generation, daily briefings, and article summaries consume a significant number of LLM tokens. To keep hosting costs minimal or zero for self-hosters, we prefer routing LLM queries (completions and embeddings) through a free LLM gateway where available, but must fall back to a standard OpenAI client if the free gateway fails or is not configured.

## Decision Drivers

- Cost optimization (prioritize free tiers/gateways).
- Reliability and robustness (always fall back to premium/paid OpenAI API when free gateway fails).
- Seamless developer and self-hoster configuration (single-key fallback compatibility).

## Considered Options

- **Option 1: Free LLM Gateway First with OpenAI Fallback**: Query the free LLM gateway first (using `FREE_LLM_API_KEY` / `FREE_LLM_BASE_URL`). If the request fails with a connection or API error (`openai.OpenAIError`), catch the error and retry the query against OpenAI (`OPENAI_API_KEY` / `OPENAI_BASE_URL`).
- **Option 2: Direct Paid-Only API**: Call OpenAI directly for all operations.
- **Option 3: Strict Separate Endpoints**: Fail immediately if the configured gateway fails, without auto-retry.

## Decision Outcome

Chosen option: **Option 1: Free LLM Gateway First with OpenAI Fallback**, because it offers the best balance of cost savings and application reliability. If the free gateway goes down, the system transparently switches to the paid OpenAI API to avoid ingestion/briefing failure.

### Consequences

- **Good (Pros)**:
  - Dramatically reduces API token costs for everyday ingestion and summarizing.
  - Transparent fallback prevents downtime during gateway outages.
  - Reuses the same request parameters (model, temperature, etc.) for both calls.
- **Bad (Cons)**:
  - Fallback requests incur a delay (waiting for primary request timeout before retrying).
  - Requires managing multiple environment variable pairs if distinct.
