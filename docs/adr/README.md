# Architecture Decision Records

Short, durable notes on *significant* decisions — the context, the choice, and its consequences — so future maintainers (and the GM) understand **why** the system is shaped the way it is. One file per decision, numbered, append-only (supersede rather than rewrite).

Format: lightweight [MADR](https://adr.github.io/madr/)-style. Copy [`0000-template.md`](0000-template.md) for a new one.

| # | Decision | Status |
|---|----------|--------|
| [0001](0001-sqlite-single-file-database.md) | SQLite as the single-file datastore | Accepted |
| [0002](0002-in-browser-babel-pinned-v7.md) | In-browser React/JSX via Babel standalone, pinned to v7 | Accepted |
| [0003](0003-star-intel-scanning-model.md) | Star-intel scanning: ground truth + accumulating uncertainty | Accepted |
| [0004](0004-ftl-jump-economy.md) | FTL jump economy (condition → fuel/spares, phased) | Accepted |
| [0005](0005-version-pinned-cdn-dependencies.md) | Pin front-end CDN dependencies to a major version | Accepted |
| [0006](0006-mcp-bearer-token-auth.md) | MCP bearer-token superuser auth | Accepted |
