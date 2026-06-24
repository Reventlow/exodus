# 0005. Pin front-end CDN dependencies to a major version

- **Status:** Accepted

## Context
The front-end loads React, Babel, Lucide and Marked from public CDNs (unpkg/jsdelivr) rather than bundling them. An **unpinned `@babel/standalone` floated to 8.0.0 overnight and broke every JSX page** with no deploy on our side (see ADR-0002) — the classic floating-dependency outage.

## Decision
Pin CDN dependencies to a major version (`react@18`, `@babel/standalone@7`, a pinned `marked`). Treat any floating CDN tag (`@latest`, bare package) as a latent production outage.

## Consequences
- (+) No more overnight breakage from upstream releases.
- (−) Security/feature updates require a conscious bump.
- Follow-up: `lucide@latest` is still floating — pin it in a future change.
