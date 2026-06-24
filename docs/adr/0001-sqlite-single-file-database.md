# 0001. SQLite as the single-file datastore

- **Status:** Accepted

## Context
Exodus is a single-GM campaign companion with a handful of concurrent users, deployed as one container on a home NAS (ZimaOS). Operational simplicity and trivial backup/restore matter far more than write concurrency or horizontal scale.

## Decision
Use **SQLite** as the only datastore — a single file on a Docker volume at `/app/data`. No external database service. (Redis is still used, but only as the Channels layer for WebSockets, not for persistence.)

## Consequences
- (+) Dead-simple ops: no DB container, backup is copying one file, restore is dropping it back.
- (+) Fast and more than sufficient at this scale.
- (−) Single-writer model — SQLite serialises writes. High write concurrency would contend; mitigated by the low user count and by wrapping shared-resource debits (FTL fuel/spares, scan grants) in `transaction.atomic` with **conditional `UPDATE`s** (since `select_for_update` is a no-op on SQLite).
- (−) No DB-level row locking; concurrency-sensitive logic must be written defensively.
