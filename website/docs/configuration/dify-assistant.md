---
title: Dify assistant
---

# Dify assistant

News Dashboard can load Dify's chat-bubble widget after a user signs in. It is
disabled by default. The browser loads Dify's embed script directly, so this
integration is appropriate for a published Dify app whose capabilities and
data are safe for every person who can use the News Dashboard instance.

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
guides describe these choices; Dify's [embedding guide](https://docs.dify.ai/en/cloud/use-dify/publish/webapp/embedding-in-websites.md)
documents the Publish → Embed flow.

For self-hosted Dify, set `ALLOW_EMBED=true` in Dify's deployment before using
the token. Consult Dify's [self-hosted environment-variable reference](https://docs.dify.ai/en/self-host/deploy/configuration/environments.md)
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

`DIFY_CHAT_BASE_URL` must be the browser-reachable HTTPS base URL of the Dify
deployment. `http://localhost` is accepted only for local development. Do not
use an internal Docker, Kubernetes, or private DNS name that a reader's browser
cannot resolve. `DIFY_CHAT_TITLE` defaults to `News Assistant` when omitted.

`DIFY_CHAT_APP_TOKEN` is the **Publish → Embed token**. It is not a Dify
service/API key and must never be replaced with one. The widget receives this
token in `/api/config` and sends it to the browser by design; treat it as a
public WebApp/embed identifier, not as a credential that protects sensitive
data. Dify web apps are public by default, so anyone with the WebApp URL or
embed token can use the published app. Keep service keys, administrator
credentials, and unrestricted data tools out of that Dify app. See Dify's
[Web App settings](https://docs.dify.ai/en/cloud/use-dify/publish/webapp/web-app-settings.md)
for its public-WebApp model.

The widget loads only after News Dashboard authentication, but Dify's supplied
user context is not authentication or authorization. News Dashboard provides
only its opaque user ID as Dify system context; it does not provide the user's
email, username, session, or News Dashboard permissions. Dify's own
[end-user identity documentation](https://docs.dify.ai/en/api-reference/guides/end-user-identity.md)
also notes that a Dify user identifier is an application-supplied identifier,
not an authentication mechanism.

### Helm

With Helm, use the structured values below. Store the embed token in a
pre-existing Kubernetes Secret; the chart does not accept a service API key.

| Helm value                | Purpose                                                                           |
| ------------------------- | --------------------------------------------------------------------------------- |
| `app.dify.enabled`        | Enables the widget. Requires `baseUrl` and `existingSecret`.                      |
| `app.dify.baseUrl`        | Browser-reachable Dify HTTPS base URL.                                            |
| `app.dify.title`          | Bubble title; defaults to `News Assistant`.                                       |
| `app.dify.existingSecret` | Name of the pre-existing Secret containing the embed token.                       |
| `app.dify.appTokenKey`    | Key in that Secret containing the embed token; defaults to `DIFY_CHAT_APP_TOKEN`. |

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

The Dify URL must be reachable from every browser that can open News
Dashboard, with a certificate trusted by that browser. Production deployments
should use HTTPS for both applications.

If Dify sits behind a reverse proxy, allow the News Dashboard HTTPS origin in
Dify's CORS policy. The embed script and its chat requests originate in the
reader's browser, not the News Dashboard server. Preserve Dify's streaming
responses: do not buffer or cache `text/event-stream` responses, and set a
response read timeout that permits a chat response to complete.

If a News Dashboard reverse proxy adds a Content-Security-Policy, allow the
specific Dify origin in the directives the widget needs:

- `script-src` for `embed.min.js`
- `connect-src` for Dify API and SSE connections
- `frame-src` for the Dify chat frame

Use the single configured Dify HTTPS origin rather than a wildcard. A proxy
that adds its own cross-origin restrictions must also permit the Dify origin;
News Dashboard's application responses do not set a CSP themselves.

## Private-data boundary

This embed integration does not grant Dify access to News Dashboard articles,
sources, or accounts. Do not give a Dify app a shared News Dashboard service
credential to make it appear personalized.

If a future Dify integration needs a user's private News Dashboard data, start
from the existing [read-only MCP server](mcp-server) boundary instead: each
user creates and revokes a scoped bearer token, and the available tools expose
only read operations for that user's visible articles. That is a separate
integration and must preserve its per-user authorization and scope checks.

## Verify and troubleshoot

1. Sign in to News Dashboard in a browser and confirm the chat bubble appears.
2. In browser developer tools, confirm `/api/config` reports enabled Dify
   configuration and that `<base URL>/embed.min.js` loads without a blocked
   request.
3. Send a harmless test message and confirm the response streams to completion.
4. For Helm, inspect `helm template` output and confirm that the token comes
   from the selected Secret rather than a literal value.

| Symptom                                             | Check                                                                                                                                                                                                                                                    |
| --------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| No chat bubble                                      | Confirm the user is signed in, `DIFY_CHAT_ENABLED=true`, a valid HTTPS `DIFY_CHAT_BASE_URL`, and a non-empty embed token. Restart after changing environment variables. Invalid or incomplete configuration fails closed and leaves the widget disabled. |
| `embed.min.js` or frame is blocked                  | Publish the Dify app, enable `ALLOW_EMBED=true` for self-hosted Dify, and allow the exact Dify origin in the reverse proxy's CSP.                                                                                                                        |
| Browser reports CORS errors or replies never finish | Allow the News Dashboard origin in Dify's CORS policy. Check proxy logs for buffered, cached, or prematurely timed-out SSE responses.                                                                                                                    |
| Dify rejects the token                              | Copy a current token from **Publish → Embed**, not an API/service key, and republish/restart as required by the Dify version.                                                                                                                            |
| A user can use an assistant they should not access  | The Dify user ID is not authorization. Remove private capabilities from the public embed or design a separate per-user, scoped integration.                                                                                                              |
