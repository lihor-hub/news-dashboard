---
title: Dify assistant
---

# Dify assistant

News Dashboard can show its own floating assistant button after a user signs
in. The button opens a responsive panel containing Dify's published WebApp in
an iframe. The integration is disabled by default and loads no third-party
script in the News Dashboard page.

Use this integration only for a published Dify app whose capabilities and data
are safe for every person who can use the News Dashboard instance.

## Choose and publish a Dify app

Choose the Dify app type that matches the assistant's job:

| App type     | Use it when                                                                                                           |
| ------------ | --------------------------------------------------------------------------------------------------------------------- |
| **Chatbot**  | A prompt- and knowledge-base-backed conversation is enough. This is the simplest choice for a general news assistant. |
| **Agent**    | The model should decide when to use Dify tools. It needs a tool-capable model and careful tool permissions.           |
| **Chatflow** | Each conversational reply must follow a defined multi-step flow, with explicit branches, retrieval, or validation.    |

Build and test the app in Dify, then select **Publish → Embed** and copy its
embed token. Dify's [Chatbot](https://docs.dify.ai/en/cloud/use-dify/build/chatbot.md),
[Agent](https://docs.dify.ai/en/cloud/use-dify/build/agent.md), and
[Workflow & Chatflow](https://docs.dify.ai/en/cloud/use-dify/build/workflow-chatflow.md)
guides describe these choices; Dify's
[embedding guide](https://docs.dify.ai/en/cloud/use-dify/publish/webapp/embedding-in-websites)
documents its WebApp iframe URL.

For self-hosted Dify, set `ALLOW_EMBED=true` in Dify's deployment before using
the token. Consult Dify's
[self-hosted environment-variable reference](https://docs.dify.ai/en/self-host/deploy/configuration/environments)
for the version-specific placement and restart procedure.

## Configure News Dashboard

Set the following values in News Dashboard's application environment, then
restart the application:

```dotenv
DIFY_CHAT_ENABLED=true
DIFY_CHAT_BASE_URL=https://dify.example.com
DIFY_CHAT_APP_TOKEN=the-token-from-publish-embed
DIFY_CHAT_TITLE=News Assistant
```

`DIFY_CHAT_BASE_URL` must be browser reachable. Production URLs must use HTTPS.
HTTP is accepted only for local development at `localhost`, `127.0.0.1`, or
`[::1]`. Do not use an internal Docker, Kubernetes, or private DNS name that a
reader's browser cannot resolve. `DIFY_CHAT_TITLE` defaults to `News Assistant`
when omitted.

Dify must use an origin separate from News Dashboard, including a different
port during loopback development. Do not reverse-proxy Dify under a path on the
News Dashboard origin. Browser validation rejects same-origin configuration so
an unsandboxed Dify WebApp cannot read the authenticated parent page.

`DIFY_CHAT_APP_TOKEN` is the **Publish → Embed token**. It is not a Dify
service/API key and must never be replaced with one. The token is returned by
`/api/config` and becomes part of the browser-visible
`<base URL>/chatbot/<token>` iframe URL by design. Treat it as a public WebApp
identifier, not as a credential that protects sensitive data. Dify WebApps are
public by default, so anyone with the WebApp URL or embed token can use the
published app. Keep service keys, administrator credentials, and unrestricted
data tools out of that Dify app. See Dify's
[Web App settings](https://docs.dify.ai/en/cloud/use-dify/publish/webapp/web-app-settings.md)
for its public-WebApp model.

### Identity and privacy

The launcher is available only after News Dashboard authentication, but News
Dashboard sends no username, email address, user ID, account permissions,
article/page context, or Dify input/system/user variables to the iframe. The
iframe URL contains only the configured base URL and embed token, with no query
string or fragment.

Dify creates and manages its own WebApp end-user and conversation identity
inside the iframe. That identity is separate from a News Dashboard account: it
does not authenticate the News Dashboard user, map a Dify conversation to that
user, or authorize access to private News Dashboard data. Closing the panel
destroys the iframe runtime, but Dify's own server-side or browser-storage
lifecycle remains governed by the Dify deployment.

### Helm

With Helm, use the structured values below. Store the embed token in a
pre-existing Kubernetes Secret; the chart does not accept a service API key.

| Helm value                | Purpose                                                                                     |
| ------------------------- | ------------------------------------------------------------------------------------------- |
| `app.dify.enabled`        | Enables the iframe assistant. Requires `baseUrl` and `existingSecret`.                      |
| `app.dify.baseUrl`        | Browser-reachable Dify base URL; HTTPS except for supported loopback development addresses. |
| `app.dify.title`          | Accessible launcher and panel title; defaults to `News Assistant`.                          |
| `app.dify.existingSecret` | Name of the pre-existing Secret containing the embed token.                                 |
| `app.dify.appTokenKey`    | Key in that Secret containing the embed token; defaults to `DIFY_CHAT_APP_TOKEN`.           |

For example:

```bash
kubectl -n news-dashboard create secret generic dify-embed \
  --from-literal=DIFY_CHAT_APP_TOKEN='the-token-from-publish-embed'

helm upgrade news-dashboard ./helm/news-dashboard \
  --namespace news-dashboard \
  --reuse-values \
  --set app.dify.enabled=true \
  --set app.dify.baseUrl=https://dify.example.com \
  --set app.dify.title='News Assistant' \
  --set app.dify.existingSecret=dify-embed \
  --set app.dify.appTokenKey=DIFY_CHAT_APP_TOKEN
```

## Browser and reverse-proxy requirements

The Dify URL must be reachable from every browser that can open News Dashboard,
must have a different origin, and must have a certificate trusted by that
browser. Production deployments should use HTTPS for both applications.

The iframe navigation goes directly from the reader's browser to
`<base URL>/chatbot/<token>`. Self-hosted Dify must permit framing with
`ALLOW_EMBED=true`. If the News Dashboard reverse proxy adds a
Content-Security-Policy, allow the exact Dify origin in `frame-src`.

No Dify JavaScript runs in the News Dashboard parent document, so this
integration does not require adding Dify to the parent's `script-src` or
`connect-src`. Iframe navigation also does not require Dify CORS to allow the
News Dashboard origin. Inside the iframe, Dify's own WebApp makes its normal API
and streaming requests. A proxy in front of Dify must not buffer or cache
`text/event-stream` responses and must allow enough response-read time for a
chat response to complete.

## Private-data boundary

This iframe integration does not grant Dify access to News Dashboard articles,
sources, accounts, or current-page context. Do not give a public Dify app a
shared News Dashboard service credential to make it appear personalized.

If a future Dify integration needs a user's private News Dashboard data, start
from the existing [read-only MCP server](mcp-server) boundary instead: each
user creates and revokes a scoped bearer token, and the available tools expose
only read operations for that user's visible articles. That is a separate
integration and must preserve its per-user authorization and scope checks.

## Verify and troubleshoot

1. Sign in to News Dashboard and confirm the floating assistant button appears.
2. Confirm no Dify request occurs before opening the assistant.
3. Open it and confirm an iframe requests `<base URL>/chatbot/<token>` without a
   query string or fragment.
4. Send a harmless test message and confirm the response streams to completion.
5. Close the panel and confirm the iframe disappears. Reopen it to retry a
   transient network failure.
6. For Helm, inspect `helm template` output and confirm that the token comes
   from the selected Secret rather than a literal value.

| Symptom                                      | Check                                                                                                                                                                                                                                                                                                |
| -------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| No assistant button                          | Confirm the user is signed in, `DIFY_CHAT_ENABLED=true`, `DIFY_CHAT_BASE_URL` uses an origin separate from News Dashboard and HTTPS in production or HTTP only at `localhost`, `127.0.0.1`, or `[::1]`, and the embed token is non-empty. Restart after changes. Invalid configuration fails closed. |
| The WebApp iframe is blocked                 | Publish the Dify app, enable `ALLOW_EMBED=true` for self-hosted Dify, and allow the exact Dify origin in the News Dashboard proxy's `frame-src`.                                                                                                                                                     |
| Replies never finish                         | Check the proxy in front of Dify for buffered, cached, or prematurely timed-out SSE responses.                                                                                                                                                                                                       |
| Dify rejects the token                       | Copy a current token from **Publish → Embed**, not an API/service key, and republish or restart as required by the Dify version.                                                                                                                                                                     |
| The assistant is not personalized by account | This is intentional. News Dashboard sends no identity or context, and Dify's WebApp identity is separate. Use a separately designed authenticated integration for private or per-user capabilities.                                                                                                  |
