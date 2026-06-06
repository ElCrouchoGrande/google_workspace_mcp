# Google Workspace MCP — Codebase Guide

## Overview

MCP server exposing Google Workspace (Gmail, Drive, Calendar, Docs, Sheets, etc.) as tools. Deployed on Railway over HTTP using FastMCP with OAuth 2.1.

Entry points:
- `fastmcp_server.py` — used by Railway (HTTP, OAuth 2.1, stateless mode)
- `main.py` — local CLI (stdio or HTTP)

## Auth Architecture

### OAuth 2.1 (Railway/HTTP)

`MCP_ENABLE_OAUTH21=true` is set. The flow:

1. MCP client connects; server returns OAuth discovery metadata
2. Client drives a Google OAuth flow; server acts as the OAuth provider
3. After consent, credentials stored under the authenticated email in `LocalDirectoryCredentialStore` (`~/.google_workspace_mcp/credentials/<email>.json`)
4. Every tool call carries a bearer token; `MCPSessionMiddleware` extracts the session ID; `AuthInfoMiddleware` populates `authenticated_user_email` in FastMCP context
5. `@require_google_service` decorator reads the session email, loads credentials, builds the Google API client, and injects it as the first (`service`) parameter

Key files:
- `auth/google_auth.py` — `get_credentials()`, `handle_auth_callback()`, `start_auth_flow()`
- `auth/credential_store.py` — `LocalDirectoryCredentialStore` (file-based) / `GCSCredentialStore`
- `auth/oauth21_session_store.py` — in-memory + file-backed session → email mapping and PKCE state
- `auth/service_decorator.py` — `@require_google_service`, `@require_multiple_services`
- `core/server.py` — `SecureFastMCP`, middleware wiring, custom HTTP routes

### Two-account setup

**Primary account** (`paul.crouch1@gmail.com`): authenticated via the normal MCP OAuth 2.1 flow.

**Joint account** (`lizzieandpaul2019@gmail.com`): authenticated via a separate browser flow at `/auth/joint`. Credentials are stored independently in the same credential store.

To switch between accounts, Gmail tools accept an `account` parameter:
- `"primary"` (default) — uses the session-authenticated user's credentials
- `"joint"` — bypasses session auth and loads `lizzieandpaul2019@gmail.com` credentials from the file store via `_authenticate_joint_service()` in `auth/service_decorator.py`

To (re-)authenticate the joint account: visit `<server-url>/auth/joint` in a browser and complete the Google consent screen as `lizzieandpaul2019@gmail.com`.

## Tool Authoring

Tools live in service-specific directories: `gmail/`, `gdrive/`, `gcalendar/`, etc.

Typical pattern:
```python
@server.tool(title="...", annotations=ToolAnnotations(...))
@handle_http_errors("tool_name", service_type="gmail")
@require_google_service("gmail", "gmail_read")
async def my_tool(service, user_google_email: str, param: str) -> str:
    result = await asyncio.to_thread(
        service.users().messages().list(userId="me", q=param).execute
    )
    return str(result)
```

Notes:
- `service` is injected by the decorator; never pass it yourself
- In OAuth 2.1 mode, `user_google_email` is also injected (removed from the exposed signature)
- `userId="me"` always refers to the authenticated user — with joint account credentials loaded, `"me"` = lizzieandpaul2019

## Scopes

Defined in `auth/scopes.py`. Scope groups (`"gmail_read"`, `"gmail_modify"`, etc.) map to actual OAuth URLs. The decorator resolves them. Adding a new tool with a scope not yet granted requires the user to re-authenticate.

## Environment Variables (Railway)

| Variable | Purpose |
|---|---|
| `GOOGLE_OAUTH_CLIENT_ID` | OAuth client ID |
| `GOOGLE_OAUTH_CLIENT_SECRET` | OAuth client secret |
| `MCP_ENABLE_OAUTH21` | Must be `true` for Railway |
| `WORKSPACE_MCP_STATELESS_MODE` | Set `true` to disable credential file writes (ephemeral containers) |
| `WORKSPACE_MCP_CREDENTIALS_DIR` | Override credential storage path |
| `WORKSPACE_MCP_BASE_URI` | Base URL (e.g. `https://your-app.up.railway.app`) |
| `WORKSPACE_MCP_PORT` | Port (Railway sets `PORT` automatically) |
| `USER_GOOGLE_EMAIL` | Default email for single-user / OAuth 2.0 mode |

## Testing

```bash
uv run pytest tests/
```

## Deployment

Deployed via Railway from `main` branch. `fastmcp_server.py` is the entrypoint (`python fastmcp_server.py`). After merging to `main`, Railway redeploys automatically.
