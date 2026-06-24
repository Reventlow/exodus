# 0006. MCP bearer-token superuser auth

- **Status:** Accepted

## Context
We wanted Claude Code, via the local `exodus-mcp` server, to read and edit **live** game data over the existing REST API for GM tasks — not just the dev database. For a single-GM tool, full per-user OAuth would be overkill.

## Decision
A middleware (`exodus/mcp_auth.py`) checks `Authorization: Bearer <MCP_API_TOKEN>`. A valid token authenticates the request as the first active **superuser** and exempts CSRF. The token is set via an env var on the container; the MCP server holds the same value. The MCP calls the same JSON endpoints the app already uses.

## Consequences
- (+) No bespoke API — the MCP reuses GM-serialised endpoints (e.g. `/api/starmap/systems/` returns ground truth for superusers).
- (+) Simple to operate; one shared secret.
- (−) The token is superuser-equivalent: must be kept secret, HTTPS-only, no granular scopes.
