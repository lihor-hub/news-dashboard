# A2A agent endpoint

News Dashboard can expose its assistant as an [A2A (Agent2Agent)](https://a2a-protocol.org)
agent so that any A2A-capable client or agent framework can discover it and ask
read-only questions over a user's news corpus. The server is built on the
official [`a2a-sdk`](https://pypi.org/project/a2a-sdk/) and speaks A2A protocol
1.0, with 0.3 backward compatibility on the same endpoint.

## What is exposed

- **Agent card** at `GET /.well-known/agent-card.json` — public discovery
  metadata (no authentication, but only served when the feature is enabled).
- **JSON-RPC endpoint** at `POST /api/a2a` — accepts `SendMessage` (and the 0.3
  `message/send` equivalent). Each incoming message is answered with a single
  agent message: the answer text plus a data part listing the source articles.

The agent has exactly one skill, `ask_news`: retrieval-augmented Q&A over the
articles visible to the token owner. It is strictly read-only — there are no
mutation skills, no streaming, no push notifications, and no task persistence.

## Enabling it

The endpoint is **disabled by default**. To enable it, set:

```
A2A_SERVER_ENABLED=true
```

The agent card advertises the JSON-RPC URL as `{base URL}/api/a2a`, where the
base URL is resolved with the documented precedence `APP_BASE_URL` →
`NEWS_DASHBOARD_BASE_URL` → `NEWS_DASHBOARD_URL`. Make sure one of these points
at the public URL of your deployment.

## Authentication

A2A calls reuse the scoped MCP bearer tokens (`mcp_tokens`): create a token in
the dashboard (requires `MCP_SERVER_ENABLED=true` for the token-management UI)
and give it the `ask` scope. Requests without a valid, unrevoked token with the
`ask` scope are rejected with `401`/`403`. Answers are always scoped to the
articles visible to the token's owner.

The token family is shared with MCP, but its scopes remain surface-specific:
A2A requires `ask`, while MCP single-article retrieval requires `read`. Neither
scope implies the other.

## Security boundaries

- Disabled unless `A2A_SERVER_ENABLED` is explicitly set.
- Bearer tokens are stored hashed; scopes are enforced per request.
- The agent can only run retrieval Q&A — no SQL, no filesystem, no shell, no
  dashboard mutations.
- Query length is bounded by the shared news-question limit to constrain
  prompt-injection amplification and payload abuse. MCP question answering is
  planned; it is not currently an available MCP tool.

## Client example

Using the official Python SDK:

```python
import asyncio
import httpx

from a2a.client import ClientConfig, create_client
from a2a.helpers import get_message_text
import a2a.types as a2a_types


async def main() -> None:
    async with httpx.AsyncClient(
        headers={"Authorization": "Bearer ndmcp_..."}
    ) as http_client:
        client = await create_client(
            "https://news.example.com",
            ClientConfig(streaming=False, httpx_client=http_client),
        )
        request = a2a_types.SendMessageRequest(
            message=a2a_types.Message(
                message_id="msg-1",
                role=a2a_types.Role.ROLE_USER,
                parts=[a2a_types.Part(text="What happened in AI this week?")],
            )
        )
        async for response in client.send_message(request):
            if response.HasField("message"):
                print(get_message_text(response.message))


asyncio.run(main())
```

Any other A2A client works the same way: resolve the agent card from
`/.well-known/agent-card.json`, then POST JSON-RPC `SendMessage` requests to
`/api/a2a` with the bearer token and an `A2A-Version: 1.0` header (0.3-style
`message/send` requests are also accepted for older clients).
