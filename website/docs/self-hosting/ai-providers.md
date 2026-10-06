---
title: AI providers and reasoning models
sidebar_position: 3
---

# AI providers and reasoning models

Choose the text provider in the server environment, then restart the app.
These settings apply to the installation's AI text features, including Ask AI,
briefings, lesson chat, quizzes, summaries, translation, and podcast scripts.
The deployment operator supplies the credentials used by all app users and
background jobs. This integration does not connect a separate ChatGPT account
for each News Dashboard user.

| `AI_TEXT_PROVIDER` | Credentials                                                                 | Default text model          | Billing                       |
| ------------------ | --------------------------------------------------------------------------- | --------------------------- | ----------------------------- |
| `gateway`          | `FREE_LLM_API_KEY` / `FREE_LLM_BASE_URL`, with the existing OpenAI fallback | Existing feature defaults   | Configured gateway/API        |
| `openai`           | `OPENAI_API_KEY` / optional `OPENAI_BASE_URL`                               | Existing feature defaults   | OpenAI API                    |
| `chatgpt`          | Protected OAuth credential file                                             | `gpt-6-luna`, medium effort | Authorized ChatGPT plan usage |
| `ollama`           | `OLLAMA_API_KEY`                                                            | `gemma4:31b`                | Ollama Cloud account          |

ChatGPT and Ollama modes do not fall back to a paid OpenAI API key on failure.
A subscription is authorized through the supported
[Sign in with ChatGPT plan-usage flow](https://developers.openai.com/siwc/token-sharing-open-source).
API billing remains separate from subscription usage. The subscription flow is
for open-source, locally hosted or self-hosted installations; a remotely hosted
commercial service requires OpenAI's separate access process.

## Luna and Sol presets

Use one of these presets with `chatgpt`, `openai`, or a compatible gateway:

| `AI_MODEL_PRESET` | Model        | Reasoning effort |
| ----------------- | ------------ | ---------------- |
| `luna-medium`     | `gpt-6-luna` | `medium`         |
| `luna-high`       | `gpt-6-luna` | `high`           |
| `sol-low`         | `gpt-6-sol`  | `low`            |
| `sol-medium`      | `gpt-6-sol`  | `medium`         |

For example:

```dotenv
AI_TEXT_PROVIDER=chatgpt
AI_MODEL_PRESET=luna-high
AI_REQUEST_TIMEOUT_SECONDS=120
CHATGPT_CREDENTIALS_FILE=/data/chatgpt/chatgpt.json
```

An explicit feature model such as `OPENAI_BRIEFING_MODEL` takes precedence over
`AI_TEXT_MODEL`, which takes precedence over the preset. Leave feature model
variables empty to use the preset across the app. `AI_REASONING_EFFORT` overrides
the preset's effort for GPT-6 models. The spelling for “med” is `medium`.
Ollama uses its own cloud model names; an OpenAI preset does not select a model
on Ollama. Use `AI_TEXT_MODEL` or a feature override to choose another Ollama model.

GPT-6 LangChain requests use the Responses API and omit temperature. Existing
short output limits are raised to at least 8,192 total output tokens to leave
room for reasoning as well as visible text. Higher effort can increase latency
and usage. See the official [Luna](https://developers.openai.com/api/docs/models/gpt-6-luna)
and [Sol](https://developers.openai.com/api/docs/models/gpt-6-sol) model references.

## Authorize your ChatGPT subscription

Run the login command on the computer where your browser runs, from a checkout
with its Python dependencies installed:

```bash
uv run python -m news_dashboard.chatgpt_auth login
uv run python -m news_dashboard.chatgpt_auth models
```

The browser asks you to authorize News Dashboard and grant ChatGPT plan usage.
The local callback listener binds to `127.0.0.1:1455`; `login --port 54321` selects
another available port. This flow registers this app's own client. Credentials
from an unrelated Codex or ChatGPT installation are not substitutes.

The default credential path is `~/.config/news-dashboard/chatgpt.json`.
Use `login --credentials /absolute/path/personal.json` to create or reconnect a
separate registration; choose it at runtime with `CHATGPT_CREDENTIALS_FILE`.
The app validates the ID token's signature, issuer, audience, expiry, and nonce
before saving the account. Reauthorization cannot overwrite that registration
with a different account. Credential files are written atomically with Unix
mode `0600`. Refreshes use a file lock and replace rotating tokens together.

For a server or container, transfer the credential file over a protected channel
such as SSH, following OpenAI's
[self-hosted VM procedure](https://developers.openai.com/siwc/token-sharing-open-source/self-hosted-vms).
Place it in a private, writable directory on the existing persistent app-data
volume, set its owner to the runtime user, and set `CHATGPT_CREDENTIALS_FILE` to
its path inside the container. Mount the directory rather than a single file:
token refresh replaces the file atomically. A read-only Kubernetes Secret mount
cannot store rotating credentials. Retain each host's own `chatgpt-host.json`
when moving credential records between hosts.

For the default Compose image, the runtime user is UID 1000 and app storage is
`/data`. The Helm chart uses `app.data.dir` for the existing writable app-data
volume. For example, configure:

```yaml
app:
  ai:
    textProvider: chatgpt
    modelPreset: sol-low
    requestTimeoutSeconds: 120
    chatgptCredentialsFile: /data/chatgpt/chatgpt.json
```

The current account's model catalog comes from `models`; account/workspace
access is only confirmed by a successfully completed inference request. Plan
limits and authorization errors are surfaced without using API-key fallback.
Review usage and app permissions in [ChatGPT Settings → Usage](https://chatgpt.com/settings/usage).

To sign out, run:

```bash
uv run python -m news_dashboard.chatgpt_auth logout
```

This revokes the renewable session before clearing tokens, while preserving the
registration identity for later sign-in. If revocation fails, the command keeps
the credential file so you can retry; disconnect the app in ChatGPT Settings if
needed.

Subscription inference sends complete text history through the public Responses
API with `store=false` and `stream=true`. It requires `response.completed` before
returning an answer; incomplete, failed, and interrupted streams are errors.
Unsupported sampling settings, output caps, and tracing metadata are omitted.
The optional tool-based Deep Agent email research is skipped in subscription
mode; canonical briefings and emails still work. See OpenAI's
[preview limitations](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations).

## Use Ollama Cloud

Store the key in the ignored `.env` file or a deployment secret:

```dotenv
AI_TEXT_PROVIDER=ollama
OLLAMA_API_KEY=your-cloud-key
AI_TEXT_MODEL=gemma4:31b
AI_REQUEST_TIMEOUT_SECONDS=120
```

The app connects directly to `https://ollama.com/v1`; it needs no local Ollama
installation. Use the exact cloud model name returned by
`https://ollama.com/api/tags`, rather than a local `:cloud` alias. See
[Ollama Cloud](https://docs.ollama.com/cloud) and
[OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility).

For Helm, put `OLLAMA_API_KEY` in `app.ai.existingSecret`, set
`app.ai.textProvider=ollama`, and optionally set `app.ai.textModel`. The key is
read from `app.ai.ollamaApiKeyKey`, which defaults to `OLLAMA_API_KEY`.
Compose forwards the provider, preset, model, effort, and feature overrides from
the host environment to the application container.

## Embeddings and audio

ChatGPT subscription credentials are for text generation. They do not replace
an embedding API key or an audio/TTS API key. Embeddings keep their existing
`FREE_LLM_*` / `OPENAI_*` configuration and `OPENAI_EMBEDDING_MODEL`; speech
synthesis uses the OpenAI API credentials.

When only ChatGPT or Ollama text access is configured, Ask AI ranks the eligible
article corpus using PostgreSQL full-text relevance instead of calling an
embedding service. It keeps the same saved/read or include-all selection, user
visibility, minimum article count, and citations. With embedding credentials
configured, Ask AI retains vector retrieval. Topic maps, embedding views, and
similarity deduplication still require an embedding provider. Podcast scripts
work with the text provider; generating spoken audio requires audio credentials.
