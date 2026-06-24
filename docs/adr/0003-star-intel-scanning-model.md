# 0003. Star-intel scanning: ground truth + accumulating uncertainty

- **Status:** Accepted

## Context
We wanted an agency-intelligence mini-game: a single source of truth per system, observatory-driven rolls, accuracy that improves with sustained effort, and a shared public record where agencies can publish — or fake — data. The dormant `AgencyScan` model (old scan levels 0–3) was reworked rather than greenfielded.

## Decision
- Each `StarSystem` holds GM **ground truth** (`resources`, `has_livable_planet`) plus `difficulty_mod`. Target successes = `15 + difficulty_mod`, clamped 5–25.
- An **observatory** rolls `5 + 5 (Ground Telescope) + 5 (Deep-Space Tracking)` dice (WoD d10, 8+ success, 10-again). Successes **accumulate monotonically** in a per-agency `AgencyScan`.
- **Uncertainty% = max(0, (target − accumulated) × 25)**, *uncapped* (so being far off can read well over 100%). The player readout is the truth fuzzed by the current uncertainty; the livable flag is revealed at ≤ 60% uncertainty.
- The GM **grants N scans per observatory** (like project rolls); the scan itself discovers an undiscovered system.
- A `PublicScanRecord` lets any agency publish real or **false** data; each active false record raises the *effective* target for everyone; players can filter the board by agency; the GM oversight page exposes `is_false`.

## Consequences
- (+) Rich strategic + disinformation play, reusing `AgencyScan` and the existing WoD roll loop.
- (+) Tunable constants in `starmap/serializers.py` (`UNCERTAINTY_PER_SUCCESS`, `LIVABLE_REVEAL_UNCERTAINTY`, `FALSE_DATA_PENALTY`).
- (−) Legacy `scan_level` / `scan_level_truth` columns left vestigial pending a cleanup migration.
- (−) Uncapped uncertainty needs UI clamping for the progress bar.
