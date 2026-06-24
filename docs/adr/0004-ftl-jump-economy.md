# 0004. FTL jump economy (condition → fuel/spares, phased)

- **Status:** Accepted

## Context
A ship's `location` was set by an unvalidated dropdown, and the class "maintenance" stat plus the `provides_ftl` "No FTL drive" warning were purely cosmetic. We wanted real, costed interstellar travel that ties into system resources without overloading a single number — shipped in phases so each was independently deployable.

## Decision
A costed jump action gated by `SiteSettings.show_ftl_jumps`:
- **Phase 1:** a jump spends hull condition (`Starship.maintenance_state`) = class maintenance × a flat rate; fail-closed if unaffordable; free resupply at a claimed system. `JumpLog` audits everything.
- **Phase 2:** an agency **fuel/spares stockpile** (`Agency.ftl_fuel`/`ftl_spares`) refilled by extracting `StarSystem.resources` at claimed + scanned systems. When the economy is active, condition drops to a small wear tick and the jump debits the stockpile via a **concurrency-safe conditional `UPDATE`**.
- **Phase 3:** execute jumps from the star map, one costed leg at a time.
- All coefficients live in `SiteSettings.jump_economy_config` (JSON) — balance changes need no migration.

## Consequences
- (+) Gives the previously-cosmetic stats real teeth; a logistics game; additive phases.
- (+) JSON config = retune without migrations.
- (−) Two cost models (condition vs fuel) selectable by config can confuse if mis-set; documented in the settings UI.
