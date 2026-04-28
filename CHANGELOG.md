# Changelog

## v0.15.32
- **Initiative re-rolls every round.** Switched from canonical "roll once at scene start" (WoD 2.0) to the Storyteller variant where every round-roll re-rolls initiative for every participant and rebuilds the order
- Behaviour: at the round-advance branch of `_advance_turn_pointer`, every participant re-rolls (`_compute_initiative`); `Encounter.initiative_order` rebuilds sorted desc by score (ties by id); active pointer resets to whoever rolled highest. The `round_advance` log row carries the full new ordering as a comma-list and a structured `rolled` payload key
- Existing round-boundary cleanup (defensive stances, aim, persistent grenade effects, burning roll-call) still fires before the re-roll so the new round opens fresh
- Rules explainer at `/rules/combat/` ROUND STRUCTURE updated — INITIATIVE bullet now reads "rolled at scene start AND re-rolled at every round boundary (Storyteller variant — chaos / momentum-driven combat)"
- No new endpoints, no schema changes, no migrations

## v0.15.31
- **Emoji icons on grenade-effect condition pills** — at-a-glance reading of who's got what:
  - 🔥 BURNING (phosphor)
  - ☀️ BLINDED (flashbang / stun grenade)
  - ☁️ SMOKE (smoke grenade)
  - 🟢 TEAR GAS (tear gas grenade)
- Implemented as a tag → emoji prefix lookup in the pill renderer; the `CONDITION_DEFS` label is unchanged so log payloads and timeline messages keep their plain ASCII (`f"{name}: SMOKE cleared"` etc.). Only the row pill carries the icon
- Rules-page GRENADES table updated to mirror the icons
- No code path changes, no schema changes — purely cosmetic

## v0.15.30
- **Burning tick is now GM-driven, not auto-applied.** v0.15.29 ticked 1L automatically at round-roll. v0.15.30 replaces that with a per-burning-participant **🔥 TICK BURN** sub-form (GM-only) on the participant's row. GM picks dice (default 1) and damage type (default L) per round. **0 dice is a valid skip** — narrative reasons like "rolled on the floor" or "soaked by sprinkler" without extinguishing
- **Round-roll roll-call** — at round-advance, the system writes a single log row naming every burning, non-incapacitated participant. Reminds the GM to tick each via their row sub-form. No automatic damage from this row
- **Reaffirmed: GM picks who's affected by grenade explosions.** The THROW GRENADE form's multi-target checkbox panel (shipped in v0.15.29) lets the thrower (or GM) explicitly check every participant in the blast — no faction restriction, friendly fire allowed. Working as designed
- New `tick_burn` view and URL (`combat:tick_burn`). New CombatLog action_type: `burn_tick`. Track-upgrade rules honoured (B can overflow to L, etc.); auto-incapacitates on track fill
- Rules explainer at `/rules/combat/` GRENADES subsection updated — BURNING bullet now describes the GM-driven flow with worked examples (1L default, 2L severe, 1B smoke inhalation, 0 skip)
- No model schema changes, no migrations, no new dependencies

## v0.15.29
- **Grenades** — new `category="grenade"` weapon catalogue type. Seven default seeds: Frag, Concussion, Smoke, Stun (Flashbang), Phosphor, Tear Gas, EMP. Each has `radius` / `effect_tag` / `effect_duration_rounds` / `damage_dice` / `damage_type` / `cover_resists` fields
- **Per-participant inventory** stored as `grenades:<type>:<count>` condition tags. GM gives grenades via the GIVE GRENADES sub-form on the participant action panel during setup
- **THROW GRENADE action** — server resolves Dex+Athletics, multi-target blast, applies damage and effect tags. Cover applies on damage-dealing grenades; bypasses on stun/smoke/tear/EMP. EMP affects AI / cyber characters only (biological targets immune)
- New CONDITION_DEFS entries: `burning`, `smoke_cloud`, `tear_gas`, `emp_disabled`. Persistent effects tracked via `<tag>_until:<round>` companion tags; cleared automatically at round_advance when expired
- **Burning ticks** — 1L per round at round-start until extinguished. GM clears via the condition × button (no auto-extinguish; an EXTINGUISH action lands in v0.15.30)
- New CombatLog action_type: `grenade_throw`. Per-target rows + system summary
- Settings UI — weapons editor accepts grenade category with radius + duration columns. Other fields stay catalogue-fixed (admin / API for fine control)
- Rules explainer at `/rules/combat/` ADVANCED ACTIONS gains a GRENADES subsection with the types table
- No model schema changes, no migrations, no new dependencies. State lives in existing JSONFields (`SiteSettings.weapons`, `Participant.conditions`)

## v0.15.28
- **Hidden encounters** for GM prep. New encounters default to `is_hidden=True` — only the GM can see them while preparing scene, participants, equipment, conditions. RELEASE TO PLAYERS button publishes; HIDE AGAIN re-hides (rare)
- Players don't see hidden encounters in their `/combat/` list, can't access the detail page (403), and the WS consumer rejects their subscription (close 4404). Three independent gates so a tampered POST or direct URL access still bounces
- The COMBAT nav link's `has_combat_visibility` template tag also excludes hidden-encounter participations — a player whose only participation is in a hidden encounter doesn't see the link until release
- Migration `combat/0004_encounter_is_hidden` adds the field with `default=False` so existing in-flight encounters remain visible after the migration applies. Form override sets `True` on new creates
- New CombatLog action types: `is_hidden_change` (on field flip via the EDIT form, with `before` / `after` boolean payload), plus the lifecycle `system` rows on RELEASE / HIDE AGAIN
- Rules explainer at `/rules/combat/` ROUND STRUCTURE gains a HIDDEN ENCOUNTERS paragraph
- New URLs: `combat:release` at `combat/<pk>/release/`, `combat:hide` at `combat/<pk>/hide/`. Both GM-only, idempotent, redirect back to detail
- Detail-page header gains an amber "🔒 HIDDEN — players cannot see this yet" banner + RELEASE TO PLAYERS button while hidden, or a muted HIDE AGAIN button while published. Aesthetic matches the WP / IMPERSONATING chip pattern (amber border + glow + monospace)

## v0.15.27
- **Removed mooks from `/rules/combat/`.** The STOCK ADVERSARIES section (table of mook stat-block templates) is gone — the catalogue is GM-facing infrastructure, not player-facing rules. Two flow-text mentions also scrubbed: the READY GATE bullet now reads "NPCs don't ready up" (was "NPCs and mooks"), and the KNOCKDOWN CONTEST bullet drops the `mook_combat_pool / 3` parenthetical
- The implementation still uses the `mook` participant kind internally (catalogue-spawned adversaries; no FK to Character/NPC; stat block on the row directly). The settings UI `/settings/ → COMBAT → Combat NPCs` still exists for GM template management. Players just don't see the term anymore on the rules page
- No code change

## v0.15.26
- **Surprise round wiring** — the `surprise_immune` field has been on `Participant` since v0.15.0 but `_compute_defense` never read it. Now does. New `is_surprise_round` flag on `Encounter.metadata` (no schema change), GM toggle on the encounter detail page, per-participant `[ALERT]` exemption with a TOGGLE ALERT sub-form. Round-1-only effect: surprised non-immune defenders get defense=0 regardless of all other modifiers
- **Off-hand reload action** — `reload_offhand` view + URL + STANCE strip button. Same cost rules as main-hand reload (turn on own turn, free off-turn). Closes the deferred item from v0.15.16
- **Shotgun range damage** — `_parse_weapon_damage` now detects multi-range strings (`"4L close / 2L long"`). Attack form gets a CLOSE / LONG range selector when relevant. Log payload tracks the chosen range band
- **Heal / Adjust HP during combat** — new GM-only `adjust_hp` endpoint and sub-form. Three integer inputs (B/L/A) clamped to 0..health_max. Auto-toggles the `incapacitated` condition based on the new total. Logs as `health_adjust` with before/after
- **All-out attack** — new attack-form checkbox. +2 dice on the attack, attacker gains `all_out_attack` condition (def_mod=-99) until round boundary. Mutex with FULL DEFENSE — server rejects ALL-OUT ATTACK if attacker already has `defense_full`. LIVE TOTAL preview reflects the +2
- **Knockdown** — new `knockdown_capable` weapon catalogue flag (firearm only, default False; seeded True on Shotgun / Twin-Barrel / Auto Shotgun). Auto-triggered on a successful hit when the weapon has the flag and the target isn't already prone. Target rolls Str+Stamina vs attacker's successes; failure = prone. Logged as `knockdown` action_type with the resistance roll. KO column added to settings UI and the rules-page weapon catalogue
- Rules explainer at `/rules/combat/` gains SURPRISE ROUND / ALL-OUT ATTACK / KNOCKDOWN subsections; AMMO & RELOAD updated for off-hand reload; HEALTH & CONSEQUENCES mentions the new GM adjust path
- New CombatLog action_types: `reload_offhand`, `health_adjust`, `knockdown`. Existing `attack` payload extended: `range_band`, `surprised`, `all_out`. New CONDITION_DEFS entry: `all_out_attack`
- No model schema changes, no migrations, no new dependencies. State lives in existing JSONFields (`Encounter.metadata`, `Participant.conditions`, `weapons` catalogue); `Participant.surprise_immune` already existed

## v0.15.25
- **Combat race-condition hardening.** Every mutation view in `combat/` is now wrapped in `transaction.atomic()`. SQLite IMMEDIATE mode serializes writers at transaction-start, so two parallel attacks against the same target can no longer lose damage by overwriting each other's state. Two `next_turn` clicks can no longer race the pointer. Two `_log` writes can no longer collide on the unique `(encounter, sequence)` constraint
- **`_log()` retry-on-IntegrityError** — defense in depth. The atomic block already prevents collisions on IMMEDIATE, but if a future backend change relaxes that, `_log` retries once on IntegrityError before re-raising. Broadcast happens AFTER commit so a Channels-layer failure can't roll back a log row
- **No-op for normal play** — combat-paced clicks (one action per second per encounter) finish well under the SQLite busy-timeout. Lock contention is invisible at the table
- **Read views unaffected** — the page-render path stays cheap; only mutation views pay the atomic cost
- **`_apply_damage` and `_advance_turn_pointer` participate in the outer transaction** — both helpers are called from already-wrapped view functions; their `save()` calls flatten into the caller's transaction. Documented in the helper docstrings
- **No model schema changes, no migrations, no new dependencies**

## v0.15.24
- **Player-ready gate** — every Character participant must toggle READY before the GM can start combat. Stops the encounter from going live before players have chosen their starting layout (weapons, armor, cover, prone, etc.)
- READY button per row, visible only during setup, on Character participants only, gated on `p.can_control` (player on own row, GM on any character). Read-only `READY` / `NOT READY` chip visible on rows the user can't control — everyone at the table sees the state
- **GM `FORCE START` override** — checkbox visible only when at least one character is unready; bypasses the gate for offline / unresponsive players
- START button form shows a `READY: N / M CHARACTERS` summary; lists unready names so the GM can chase the holdouts
- State stored as `"ready"` flat tag on `Participant.conditions` — no schema change. Auto-stripped from every participant when combat goes live (it's a setup-only flag). Rewinding via CLEAR INITIATIVE does NOT auto-re-ready — players opt back in
- New CombatLog action_type: `ready_change`. Real-time WS fan-out picks up toggles automatically
- NPCs and mooks don't need to ready up (GM-controlled)
- Rules explainer at `/rules/combat/` ROUND STRUCTURE gains a READY GATE subsection

## v0.15.23
- **Equipping a weapon costs the turn during active combat.** WoD 2.0: drawing or switching a weapon during a fight is an action. The rule is now enforced server-side on both `equip_weapon` and `equip_offhand`. Setup-phase prep stays free (the encounter hasn't started); concluded encounters also free (post-mortem cleanup)
- **Unequipping is always free** — dropping a weapon is a WoD 2.0 free action. Only NEW equips trigger the cost
- **GM `instant_equip` override** — superuser-only checkbox on the form; bypasses both the active-turn check and the turn cost. For narrative beats ("the bandit drops his rifle and pulls a knife in the same instant")
- **Action-cost behaviour** mirrors `full_defense` / `dodge` / `aim`: marks `acted_this_round=True` but does NOT auto-advance the pointer. The GM still clicks NEXT TURN
- **UI hints** — EQUIP forms now show "⚠ COSTS YOUR TURN" on the active actor's row, and "Wait for your turn (or unequip — that's free)" on everyone else's. A muted "Equipping is free during setup; costs an action once combat starts." preamble sits at the top of the action panel during setup
- **CombatLog `weapon_change` payload extended** with `action_cost: "turn" | "free" | "instant"` so the timeline shows the cost mode
- **Rules explainer** at `/rules/combat/` ROUND STRUCTURE gains a small ACTION COSTS table (drop / equip-setup / equip-active / off-hand / GM override / reload) plus a TURN-line tweak that flags weapon-draw as an action and points readers at the new table
- No model schema changes, no migrations, no new dependencies. State already lives in `Participant.acted_this_round`

## v0.15.22
- **Wound-penalty merits now auto-applied in combat.** *Increased Pain Threshold* reduces the wound penalty by 1 toward zero at every tier (−1 → 0, −2 → −1, −3 → −2); *Pain Tolerance* short-circuits the penalty to 0 regardless of damage taken. Pain Tolerance overrides Increased Pain Threshold when both are present. The participant row's WP chip and the attack pool breakdown reflect the reduced value automatically — the GM no longer applies these by hand
- **Merit description sweep** — five combat-relevant merit definitions updated in production via MCP to flag their integration status:
  - **Increased Pain Threshold** (id 13) — auto-detected since v0.15.22
  - **Pain Tolerance** (id 18) — auto-detected since v0.15.22
  - **Berserker** (id 23) — explicitly flagged as **not yet auto-applied** (frenzy state is GM-tracked); points to the GM modifier input
  - **Concentration** (id 27) — flagged as **not yet auto-applied** ("distracting circumstances" is GM-judgement-driven)
  - **Daredevil** (id 5) — flagged as **not yet auto-applied** ("risky" is a GM ruling)
- **Refactor** — extracted `_has_named_merit(actor, merit_name)` as a generic merit-presence helper. Mirrors the canonical-M2M-then-legacy-JSON resolution model from v0.15.16. `_has_ambidextrous_merit` now delegates to it (one-liner). `_wound_penalty` calls it twice (Pain Tolerance check first, then Increased Pain Threshold)
- **Rules explainer** at `/rules/combat/` WOUND PENALTIES subsection updated — replaced the "GM applies by hand" note with the canonical "auto-detected as of v0.15.22" wording, the override semantics, and a callout that Berserker/Concentration/Daredevil remain manual

## v0.15.21
- **Martial Arts and Fencing merits now auto-apply +rating dice in combat.** Martial Arts adds +rating to Brawl attacks (unarmed strikes, grapples, improvised-by-fist); Fencing adds +rating to Weaponry attacks (knives, batons, swords, hammers, axes, etc.). Detection runs on the canonical `Character.character_merits` (or `NPC.npc_merits` for NPC actors) M2M to `MeritDefinition` — case-insensitive `name__iexact` match — plus the through-row's `rating` int field
- **The merit catalogue descriptions were updated in production via MCP earlier in this session:** both Martial Arts (id 17) and Fencing (id 8) now read "+rating dice when attacking with [Skill]" and reference v0.15.21+ auto-detection. Their `effects.skill_dice_bonus` field carries `{"Brawl": 1}` / `{"Weaponry": 1}` (the per-rating multiplier — currently unused, reserved for future tuning)
- **Live attack pool preview** shows `+ MARTIAL ARTS N` / `+ FENCING N` on the breakdown line under DEX/POOL + SKILL + WEAPON. The LIVE TOTAL span includes the bonus automatically because the server-side `_attack_preview.total` is what seeds `baseTotal` in the inline JS — no JS changes needed
- **Attack log payload extended** with `skill_merit_name` (str or null) and `skill_merit_bonus` (int) on every per-target row (blocked / miss / hit). Message tail appends `(MARTIAL ARTS +N)` or `(FENCING +N)` after the existing tails when the bonus fires; payload keys are always present so timeline filters can group on them without absence-checking
- **Off-hand attacks honour the bonus too** — if the off-hand weapon is melee and the actor has Fencing, the off-hand pool composition (`_actor_total_pool` against off-hand `weapon_data` with the auto-picked off-hand skill) hits the same `_attack_dice_pool` path and inherits the bonus. Same for a Brawl-ish off-hand under Martial Arts
- **Player override of skill** — if the player types "Brawl" by hand into the SKILL field (overriding the auto-pick), Martial Arts still fires. The resolved skill drives detection, not the auto-pick. Case-insensitive fallback in `_skill_merit_bonus` shields against casing drift
- **Defense in depth** — `_skill_merit_bonus(actor, skill_name)` returns `(None, 0)` for: mook actors (no character / NPC sheet), empty / whitespace skill_name, skill_name not in `SKILL_MERIT_MAP`, missing source FK (Character / NPC was deleted with `on_delete=SET_NULL`), missing through-row, and rating == 0. The bonus NEVER applies when the merit isn't present — the server is authoritative
- **Does NOT apply to non-attack rolls** — dodge and initiative bypass `_attack_dice_pool` entirely. A future melee-parry surface that wants the bonus will need explicit wiring
- **`merits_old` legacy JSONField is intentionally NOT consulted** — it stores names without ratings, so it can't drive a per-rating bonus reliably. Players whose merits sit in the legacy layer should re-attach them canonically (the agency / character editor already handles this)
- **New helpers** in `combat/views.py`: `SKILL_MERIT_MAP` (skill name → merit name) and `_skill_merit_bonus(actor, skill_name) → (name_or_None, rating_int)`. `_attack_dice_pool` and `_attack_preview` both call the helper; `_resolve_single_attack` re-derives it for the log tail and payload keys
- **Rules explainer** at `/rules/combat/` ADVANCED ACTIONS gains a SKILL-DICE MERITS subsection between WOUND PENALTIES and AIMING, covering the auto-apply model, the two skill bindings, the stacks-with list, the detection path, the non-attack-roll exclusion, and the timeline / UI surface
- No model schema changes, no migrations, no new dependencies. Reuses the existing `CharacterMerit.rating` / `NpcMerit.rating` through-table fields and the `MeritDefinition` catalogue

## v0.15.20
- **Rules clarification: wound penalties.** Promoted to its own subsection at the top of ADVANCED ACTIONS in `/rules/combat/`, ahead of AIMING. The previous wording in HEALTH & CONSEQUENCES was off-by-one ("when the last three boxes are unfilled, take −1") — replaced with the canonical "the rightmost three boxes carry −1 / −2 / −3 penalties (left → right)" plus a worked-example table for a 7-box track (damage 0–4 → 0; 5 → −1; 6 → −2; 7 → −3 / incapacitated)
- New section also calls out the `MOD` chip (combined wound + condition) and `WP` chip (wound alone) on the participant row, and notes that the *Increased Pain Threshold* / *Pain Tolerance* merits are not yet auto-detected by the combat module (GM applies by hand for now)
- **No code change** — the implementation has been correct since v0.15.5 (`_wound_penalty()` returns 0 / −1 / −2 / −3 based on damage total vs `health_max`; applied to every dice pool routed through `_actor_total_pool`). This release just fixes the rules text and surfaces the rule next to the other every-roll modifiers (aim, burst, conditions, gun fu, X-again)

## v0.15.19
- **Weapon-specific X-again threshold** (10 / 9 / 8) on the firearm catalogue. Default 10 for every existing entry — preserves v0.15.18 behaviour exactly. GM configures per-weapon via `/settings/ → COMBAT → Weapons → AGAIN`. No default catalogue weapon ships with anything other than 10-again — leave it to the GM's table
- **The success threshold stays at 8+ at every tier** — the X-again number is the explosion trigger only, not a different success threshold. 9-again means dice exploding on 9 or 10. 8-again means dice exploding on 8 / 9 / 10. The success count doesn't change between tiers
- `_roll_pool` now takes an `again_threshold` keyword (default 10); `_resolve_single_attack` reads it from the equipped weapon's snapshot. Off-hand uses its own snapshot independently. Dodge and initiative stay 10-again (no weapon involved)
- Structured dice payload gains an `exploded` flag — True when the die's face triggered a re-roll. Renderer uses this to glow ANY trigger-face (no longer hardcoded to 10). 9-again 9s now light up the same way 10s do. The CSS class `.die-ten` is renamed to `.die-trigger` (same styling: bold + glow)
- **Backwards-compat:** legacy log rows (pre-v0.15.18 flat int lists, or v0.15.18 structured rows missing `exploded`) back-fill the flag conservatively (`face == 10`). Pre-v0.15.19 9-again attacks won't show 9s glowing because the threshold wasn't recorded — only forward-looking attacks get the precise rendering. Initiative rendering also adopts `die-trigger` for the lone 10
- **`9-AGAIN` / `8-AGAIN` badge** on the participant row next to the equipped weapon name, both main-hand and off-hand. Mono pill, primary border + glow, in the AUTO / MAG family. Suppressed for the default 10 to keep the row uncluttered
- **Settings UI** gains an AGAIN integer column in the firearm weapons editor (parallel-array `weapons_firearm_again`, paired row-for-row with the AUTO and MAG columns). Helper `_clamp_again` in `exodus/models.py` enforces `{8, 9, 10}` with 10 fallback; reused by the form POST handler and by the `api_weapons` POST / `api_weapon_detail` PUT JSON endpoints. Combat carries a deliberate local copy `_clamp_again_local` to avoid a cross-app import
- **CombatLog `attack` payload** extended with `weapon_again: int` so the timeline can read which trigger value was active per row even after the catalogue is re-tuned
- **Rules explainer** at `/rules/combat/` ADVANCED ACTIONS gains an X-AGAIN subsection (between BURST and AUTOFIRE SPREAD) covering the three tiers, the success-threshold-stays-at-8 clarification, the 5-level chain cap, the per-weapon configuration model, and the no-default-non-10 note
- No model schema changes, no migrations, no new dependencies. Field lives in the existing `weapons` JSONField on `SiteSettings`

## v0.15.18
- **Dice rendered visually in the combat timeline.** Every attack / dodge / initiative log row now shows the actual dice faces below its message, with markup distinguishing successes (8+) from failures, 10-again explosions from base rolls, and Gun Fu auto-successes from rolled successes
- Bold + glow on 10s (the trigger) · solid primary on 8/9 successes · muted dim on 1-7 failures · dashed border + ↳ arrow prefix on explosion re-rolls (so the chain is visible) · amber `+N GUN FU` chip after the dice when an auto-success was credited
- `_roll_pool` now returns structured dice (`{face, kind, from_index, success}`) instead of a flat int list. Renderer accepts both shapes — legacy flat-list payloads from pre-v0.15.18 log rows still render (without explosion markers, because the chain wasn't recorded). Fully backwards-compatible
- New template tag `render_combat_dice` in `combat/templatetags/combat_tags.py`
- New helper `_normalize_dice_payload` in `combat/views.py` exported for the template tag's late-import use
- Per-row `data` JSONField payload unchanged in name (`dice`, `gun_fu_bonus_successes`) — only the internal shape is richer
- No schema changes, no migrations, no new dependencies

## v0.15.17
- **Gun Fu merit** (soldier-only, 1-5 dots) now grants free auto-successes in firearm combat. Each dot = 1 free success per session, spent inside an attack action. Wires the merit into the combat resolver — soldiers paying for the dots now actually get a payoff in encounters
- **GUN FU (+N SUCCESS) input** on the attack form. Player declares an integer total spend `N` (capped server-side at remaining session uses). Visible only when the actor is a soldier with the merit attached, has remaining uses, and the equipped main-hand weapon is a firearm
- **Distribution** — server spreads the declared total evenly across all targets in the action (primary + autofire spread extras + off-hand on dual-wield). Integer remainder lands on the first targets in declaration order: primary first → spread extras in their normal order → off-hand last. Examples: 5 uses across 4 targets = `2 / 1 / 1 / 1`; 3 uses across 2 targets (dual-wield) = `2 / 1`; 5 uses across 1 target = `5`; 7 uses across 4 targets = `2 / 2 / 2 / 1`
- **Effect** — bonus successes are added to the rolled success count *after* defense/cover are applied. They do **not** bypass full cover (blocked shots stay blocked) but they **do** turn a 0-success roll into a hit (auto-successes are real successes for damage math)
- **Persistence** — spent uses are written to `Character.merit_uses["Gun Fu"]` immediately after the action. The character sheet's existing REMAINING THIS SESSION counter reflects the new total on next load. GM resets per-session counters via the existing `resetMeritUses` action on the sheet
- **Defense in depth** — `_gun_fu_state(actor)` returns `(0, 0, 0)` for mooks (no character FK), NPCs (no per-session merit-use tracking), characters without the Gun Fu merit, and non-soldier characters (canonical class check). Non-firearm attacks zero out the spend server-side regardless of the form input. Cap-at-remaining via `min(uses_requested, remaining)` makes a tampered POST harmless
- **CombatLog `attack` payload extended** with `gun_fu_bonus_successes` (per-row int — the slot from the distribution), `gun_fu_total` (action-wide spend), and `gun_fu_rating` (the actor's dot count). Per-target rows carry a `(GUN FU +N SUCC)` message tail when the bonus is positive. A summary `system` row records the action-wide spend + remaining count
- **New helpers** in `combat/views.py`: `_gun_fu_state(actor)` and `_distribute_gun_fu(total, n)`. `_resolve_single_attack` gains a `bonus_successes: int = 0` kwarg threaded from the attack view's distribution
- **Rules explainer** at `/rules/combat/` extended with a GUN FU (SOLDIER ONLY) subsection covering eligibility, activation, distribution math + worked examples, the cover-doesn't-bypass rule, the non-firearm zero-out, persistence to `merit_uses`, and the per-row timeline payload
- No schema changes, no migrations, no new dependencies. Reuses existing `Character.merit_uses` JSONField and `CharacterMerit.rating` field

## v0.15.16
- **Dual-wielding** — equip a second weapon as off-hand via the EQUIP OFF-HAND sub-form on the participant action panel. Off-hand has its own snapshot (`offhand_weapon_name` + `offhand_weapon_data`) so catalogue edits don't retroactively mutate equipped off-hands. Empty submission unequips; un-equipping or swapping in a non-firearm strips any stale `offhand_ammo:*` tag
- **Off-hand ammo** tracked separately as an `offhand_ammo:N` condition tag, mirroring the main-hand `ammo:N` shape. Off-hand magazine fills on equip when the catalogue entry is a firearm with `magazine > 0`. Decrements by 1 round per off-hand attack (single-shot only in v0.15.16). New OFF-MAG indicator on the participant row reads independently of the main MAG; an OFF-HAND EMPTY pill flags a dry off-hand firearm
- **DUAL ATTACK checkbox** on the attack form (visible only when an off-hand is equipped) — fires both weapons against the primary target in one action. Main-hand attack: full pool with aim, burst, willpower, specialisations, autofire spread. Off-hand attack: −2 dice penalty (waived by Ambidextrous), no aim, no WP +3, no burst (always single), no autofire spread, same defense / cover / armor resolution per target. Off-hand uses its own weapon's dice modifier and auto-picked skill via `_weapon_skill_for(offhand_data)`
- **Ambidextrous merit detection** — checks the canonical M2M `merit_entries` (case-insensitive `name__iexact="Ambidextrous"` filtering directly on `MeritDefinition.name`, with the ORM JOINing through the `CharacterMerit` / `NpcMerit` through-tables) plus the legacy `merits_old` JSONField (free-text dict-or-string entries). Mooks have no merits → always False. When detected, the off-hand penalty is waived. UI label adapts: `AMBIDEXTROUS — no penalty` vs `−2 dice off-hand`
- **Off-hand reload is NOT implemented in v0.15.16** — when an off-hand firearm runs dry it stays empty until re-equipped (which refills via the EQUIP OFF-HAND form). Listed as a deferred item in the rules explainer; v0.15.17+ may add a dedicated off-hand reload action
- **Defense in depth** on the dual flag — `dual_attack=1` is honoured only when the attacker actually has an off-hand equipped. A tampered POST or stale form submission silently degrades to a single main-hand attack (no flash, no rejection). Off-hand-out-of-ammo gating during DUAL ATTACK skips the off-hand resolve and writes a `system` row "off-hand out of ammo, skipped" — the main-hand attack still lands cleanly
- **DUAL-WIELDING subsection** added to ADVANCED ACTIONS in `/rules/combat/`, covering equip flow, dual-attack flow, main vs off-hand pool composition, Ambidextrous waiver, separate ammo tracking, and the deferred off-hand reload
- **Schema** — migration `combat/0003_participant_offhand` adds two fields to `Participant`: `offhand_weapon_name` (`CharField(max_length=120, blank=True, default="")`) and `offhand_weapon_data` (`JSONField(default=dict, blank=True)`). Safe defaults — pre-v0.15.16 rows simply have no off-hand equipped; no data backfill required
- **CombatLog `attack` payload extended** with `dual_wield: bool`, `dual_wield_offhand: bool`, `dual_wield_penalty: int`, `ambidextrous: bool`. The off-hand attack writes a separate `attack` row with `dual_wield_offhand=True` and a message tail of `(OFF-HAND)` or `(OFF-HAND, AMBIDEXTROUS)`. The off-hand row carries its own (independent) ammo accounting via the parallel tag — main-hand keys are not re-used so the timeline doesn't get confused about which magazine drained. The `weapon_change` payload gains `offhand: bool` to distinguish main-hand vs off-hand equip rows
- **New helpers** in `combat/views.py`: `_parse_offhand_ammo_tag(tag)`, `_offhand_ammo_state(participant)`, `_set_offhand_ammo(participant, rounds)`, `_strip_offhand_ammo(participant)`, `_has_ambidextrous_merit(actor)`. Plus `equip_offhand(request, pk, participant_id)` view and `combat:equip_offhand` URL name
- **Encounter page** annotates each participant with `has_offhand`, `offhand_ammo_state`, `offhand_ammo_max`, and `is_ambidextrous` so the row template can render the off-hand chrome and the DUAL ATTACK label without a second DB walk
- No new dependencies; no other model changes

## v0.15.15
- **Ammo tracking** for firearms. Each catalogue firearm entry gains a `magazine` integer (defaults `0` at read time for legacy entries — read as "no ammo concept", preserves pre-v0.15.15 unlimited-ammo behaviour). Ten default firearms ship with mag sizes: Hand Gun 15 / Large Hand Gun 8 / SMG 30 / Assault Rifle 30 / DMR 10 / Shotgun 6 / Twin-Barrel 2 / Auto Shotgun 8 / Scoped Rifle 5 / Taser (Cartridge) 1
- **Mag fill on equip + start.** When a Character / NPC participant equips a firearm, the magazine fills automatically to the catalogue size. When `start_encounter` runs, any pre-equipped firearm also gets its mag filled (one-shot system row "Magazines filled at combat start (n participants)."). State stored as an `ammo:<N>` condition tag — no schema change required, mirrors the established `dodging:N` / `aiming_at:tid:turns` pattern
- **Burst ammo cost.** Single shot = 1 round; short burst = 3; medium = 10; long = 20. If the mag is insufficient for the requested mode, the server silently downgrades to single and logs a `system` warning ("Insufficient ammo for {mode} burst (X/Y) — fired single instead."). If completely empty, the attack is rejected with an `OUT OF AMMO — RELOAD FIRST.` flash and a system row noting the attempt
- **RELOAD action.** New `reload_weapon` view + `combat:reload` URL name. Resets ammo to the catalogue magazine size. Costs the turn when called by the active participant (`acted_this_round=True`, no auto-advance — matches `full_defense` / `dodge` / `aim`); off-turn reloads (GM bookkeeping between rounds) are free but flagged with a `system` "out-of-band reload" log row. Players have unlimited magazines (no reserve tracking) so reload is always available. Rejects non-firearm equipped weapons and firearms with `magazine <= 0` (legacy / hand-edited catalogue entries)
- **Note on naming:** the view callable is `reload_weapon` to avoid shadowing Python's `reload` builtin at module scope; the URL name remains the natural `combat:reload`
- **MAG x/y indicator** on the participant row, colour-coded `green` (≥50%) / `amber` (25–50%) / `red` (<25% or 0). Empty magazines also surface an `EMPTY — RELOAD` red pill so the OUT-OF-AMMO rejection isn't a surprise
- **RELOAD button** on the STANCE strip alongside FULL DEFENSE / DODGE / PASS TURN / AIM. Only rendered when the equipped weapon is a firearm with a positive magazine. Disabled when the magazine is already full. Live-displays the count: `RELOAD (7/15)`
- **FIRE MODE per-option ammo costs.** Each select option spells out its rounds-fired cost: `SINGLE (1 rd)`, `SHORT BURST (3 rd, +1)`, `MEDIUM BURST (10 rd, +2)`, `LONG BURST / FULL AUTO (20 rd, +3)`. Inline JS greys out options that exceed the current mag and shows an `Insufficient ammo: would downgrade to SINGLE.` muted-red note. Front-end is informational only — the server is the source of truth and silently downgrades on submit
- **Rules explainer** at `/rules/combat/` covering AIMING / BURST FIRE / AUTOFIRE SPREAD / AMMO & RELOAD with the exact dice math (single/+0, short/+1, medium/+2, long/+3), spread caps (medium 3 targets, long 6 targets), per-extra penalty (cumulative −1), aim breakage rules, ammo costs, and reload behaviour. Section follows FREE ACTIONS, before the live WEAPONS CATALOGUE
- **Live WEAPONS CATALOGUE on `/rules/combat/`** gains a MAG column for the firearm section (other categories keep the leaner four-column layout — no magazine concept on melee / improvised / thrown)
- **Settings UI** (`/settings/` → COMBAT → WEAPONS) gains a MAG integer column for firearm rows. Persisted via a parallel `weapons_firearm_magazine` array that pairs row-for-row with the AUTO flag and the visible columns — robust against row deletions / re-orderings. Coerced to a non-negative int on submit, capped at 999. Non-firearm rows render no MAG column
- **API surface** (`/api/admin/weapons/`) accepts the `magazine` field on POST / PUT for firearm entries. Coerced to a non-negative int, capped at 999. Silently dropped on non-firearm rows
- **New helpers** in `combat/views.py`: `_parse_ammo_tag(tag)`, `_ammo_state(participant)`, `_set_ammo(participant, rounds)`, `_strip_ammo(participant)`. Module-level constant `BURST_AMMO_COST = {single: 1, short: 3, medium: 10, long: 20}`. `equip_weapon` fills / strips the ammo tag. `start_encounter` tops up pre-equipped firearm mags. `attack` reads / decrements ammo and gates on empty / insufficient
- **Ammo state lifecycle:** set on equip → set on combat start (if not already set) → decremented on attack (post-roll, once per attack regardless of spread targets) → refilled on reload → stripped on un-equip / non-firearm equip
- **Mooks remain ammo-free** (their weapon is a free-text catalogue label, not a snapshot dict — no per-participant magazine state to manage). Non-firearm weapons skip the ammo system entirely
- **CombatLog `attack` payload extended** with `ammo_tracked`, `ammo_before`, `ammo_after`, `rounds_fired`, `mag_size`, `burst_downgraded_due_to_ammo`. New `action_type="reload"` row carries `magazine`, `mag_size`, `on_turn`, `weapon_name`. `weapon_change` payload gains `magazine` and `magazine_full`
- **Fix:** three multi-line `{# #}` Django template comments in `base.html`, `combat/encounter.html`, and `combat/list.html` were leaking through to the rendered page. Converted to `{% comment %}{% endcomment %}` blocks. Same bug pattern as v0.14.54 — single-line `{# #}` is single-line only
- No schema changes, no migrations, no new dependencies

## v0.15.14
- **AIM action.** New full-turn action that grants `+1` cumulative dice on the next attack against the aimed target, stackable up to `+3` over consecutive aim turns (re-aiming the same target). State lives in the participant's conditions list as a single tag of shape `aiming_at:<target_id>:<turns>` — no schema change. Aim breaks on damage taken, on full defense, on dodge, on attacking a different target, and at the round boundary (round-roll strips every aim tag across the encounter). Switching aim to a different target resets the bonus to `+1`. Players can self-cancel via × on the AIM banner; the existing prefix-aware `clear_condition` family handler strips the whole `aiming_at:*` family in one shot
- **Burst fire.** New `burst_mode` field on the attack form: `single` (default) / `short` (+1 dice) / `medium` (+2) / `long` / full auto (+3). The selector is enabled only when the equipped weapon's catalogue entry has `auto_capable: True`; non-auto firearms render only the SINGLE option (the select is disabled with a tooltip explaining why). Server-side fallback: a tampered POST trying to spend burst dice on a non-auto weapon silently downgrades to single and writes a `system` log row noting the attempt
- **Autofire spread.** Medium / long bursts can engage extra targets via an `extra_target_ids` checkbox panel that toggles visibility based on the FIRE MODE select. Each spread target rolls a separate attack at `-1 * spread_index` cumulative dice penalty (first extra `-1`, second `-2`, etc.), with its own defense / cover / armor mitigation. Caps: medium burst max 2 extras (3 targets total), long burst max 5 extras (6 targets total). Server filters out self / primary-target / unknown ids and orders extras deterministically by `(position_order, id)`
- **Aim only applies to the primary target on a burst spread.** Extras get the burst bonus but not the aim bonus. Log payload includes `aim_only_on_primary: True` when this branches
- **LIVE TOTAL preview** updates client-side when the FIRE MODE select changes (adds the burst bonus). The autofire-extras `<details>` panel and a `(SPREAD: extras roll separately at -1 cumulative)` muted hint toggle visibility together when burst mode is medium / long
- **Attack-row log payload extended** with `burst_mode`, `burst_bonus`, `aim_bonus`, `aim_consumed`, `aim_broken`, `aim_only_on_primary`, `extras_total`, `spread_index`, and `spread_penalty`. Per-spread `attack` rows carry `(BURST SPREAD #N)` message tails; a final `system` summary row lists all targets and the burst mode (`{name} unleashed {mode} burst — primary: {prim}, spread: {N} additional target(s).`)
- **Weapons catalogue gains an `auto_capable` flag** for firearm entries. Read-time default is `False` so legacy entries (and non-firearm rows) collapse to single-shot without a data migration. Three default firearms ship as auto-capable: `Sub Machine Gun`, `Assault Rifle`, `Auto Shotgun`. The other firearms (`Hand Gun`, `Large Hand Gun`, `DMR`, `Shotgun`, `Twin-Barrel Shotgun`, `Scoped Rifle`, `Taser (Cartridge)`) ship explicitly as `auto_capable: False`
- **Settings UI exposes the auto_capable checkbox** in the WEAPONS row editor (`/settings/` → COMBAT → WEAPONS). Persisted via a parallel hidden input (`weapons_firearm_auto_capable_flag`) that the visible checkbox toggles in lock-step — robust against row deletions / re-orderings. Non-firearm rows render no AUTO column (the burst-fire UI is firearm-only)
- **API surface** (`/api/admin/weapons/`) gains the `auto_capable` field on POST / PUT for firearm entries; the field is silently dropped on non-firearm rows. Sent as a JSON `bool`, persisted as a Python `bool`
- **New helpers** in `combat/views.py`: `_weapon_is_auto_capable(weapon_data)`, `_parse_aim_tag(tag)`, `_aim_state(participant)`, `_strip_aim(participant)`. Module-level constants `BURST_BONUSES = {single: 0, short: 1, medium: 2, long: 3}` and `BURST_MAX_EXTRAS = {single: 0, short: 0, medium: 2, long: 5}`. The attack view delegates per-target resolution to a new `_resolve_single_attack` helper so primary + spread share the same code path
- **Aim consumption / strip lifecycle.** `attack` consumes aim on a matching primary target and strips it silently on a different primary target (logs a `system` "aim broken — engaged different target" row). `full_defense` and `dodge` strip aim and log a clarifying `system` row. `_apply_damage` strips aim when the target takes damage (handled inside the helper so every caller benefits). Round-advance in `_advance_turn_pointer` strips every aim tag across the encounter alongside the existing stance clear
- **AIM stance button** added to the STANCE strip on the active participant's row, after PASS TURN. Wraps the target picker in a `<details>` reveal so the strip stays compact. **AIM banner** appears on every viewer's screen when a participant is aiming (cyan pill with target name and turn counter, plus × CANCEL AIM for the controlling user)
- **New `aim` POST endpoint** at `/combat/<id>/participants/<id>/aim/` with `_gm_or_owner` permission and `csrf_protect`. Rejects non-active encounter, non-active actor, missing target, and self-target. Marks `acted_this_round=True` (eats the turn) but does NOT auto-advance the pointer — matches the `full_defense` / `dodge` pattern; only `pass_turn` auto-advances. New CombatLog `action_type="aim"` row with `data` keys `turns`, `bonus`, `turns_clamped`
- **Player allow-lists extended.** `clear_condition` adds `aiming_at` to the player self-clear set so a player can × CANCEL AIM on their own row's banner
- No schema changes, no migrations, no new dependencies

## v0.15.13
- **PASS TURN action** — active participant (player or GM-driven) can voluntarily end their turn without acting. New button appears on the active row's STANCE strip, only on the active participant's own turn. Auto-advances the pointer (same logic as NEXT TURN), unlike attack/dodge/full-defense which only mark `acted_this_round` and let the GM advance manually
- Logged as `pass_turn` action_type with the participant's name; followed by the standard `turn_advance` (or `round_advance` on wrap) row from the shared advance helper
- Refactored: extracted `_advance_turn_pointer(encounter)` from `next_turn` so `pass_turn` reuses the same round-rollover, stance-clear, and dodge_pending carry-over logic without duplication
- Permission model: `_gm_or_owner()` decorator + active-participant check, so a player cannot pass for someone else's character

## v0.15.12
- **Bidirectional damage sync.** Adding a Character or NPC to an encounter now snapshots their current `health_bashing/lethal/aggravated`, `willpower_current`, and `mental_load` from the canonical sheet (was: 0/0/0/0/0). Wounded characters enter combat with their wounds already on the participant row, and wound penalties apply from join. `health_max` is recomputed at join (Size + Stamina) so a Stamina change since the last fight is reflected immediately
- **End-of-combat commit.** When the GM clicks END, every Character / NPC participant's snapshot is written back to their canonical sheet (`health_bashing/lethal/aggravated`, `willpower_current`, `mental_load`). Mooks are skipped (no sheet). FK `SET_NULL` (sheet deleted mid-combat) is also skipped. Each commit writes a `health_commit` CombatLog row with `before` / `after` payloads; a final `system` row summarises `count` of participants updated
- **Skip-commit checkbox** on the END form for test fights, dream sequences, or "what if" scenarios. The button is now wrapped in a `<details>` reveal — the GM can tick `Skip sheet commit (test fight / dream sequence)` before confirming. When ticked, the encounter ends with a single `system` row "End-of-combat sheet commit SKIPPED by GM…" and canonical sheets are untouched
- **Confirm dialog wording reflects the chosen mode.** Without skip: "End encounter and commit damage to character sheets?". With skip ticked: "End encounter WITHOUT committing damage to sheets?"
- **Real-time WS fan-out** automatically picks up the new `health_commit` events via the existing `_log()` broadcast chokepoint — any open browser subscribed to the encounter's WebSocket sees commits live, no extra plumbing required
- **Edge case — snapshot wins on commit.** If the GM manually edited the canonical sheet during combat (e.g. healed 1 lethal via the character page), that edit is overwritten when the encounter ends. Use the `skip_commit` checkbox to opt out and preserve the canonical state
- **Join-time `health_at_join` payload** added to the participant-add `_log()` data so the timeline shows pre-existing wounds (`{bashing, lethal, aggravated, willpower_current, willpower_max}`). Mooks always join at full since the catalogue carries no damage state
- Both the web form (`participant_add`) and the JSON API (`api_encounter_participants`) get the join-time copy, so MCP / external callers also benefit
- No schema changes, no migrations, no new dependencies — only `combat/views.py` and `templates/combat/encounter.html` change
- GM-only mutation paths unchanged: players cannot trigger the commit, but they will see their character's sheet updated when the GM ends the encounter

## v0.15.11
- **Fix:** `+ ADD PARTICIPANT → FROM NPCS` no longer hides agency dossiers. The previous `is_npc_dossier=False` filter masked every NPC dossier (the GM's antagonist roster), so the dropdown only listed the player-assigned NPCs — which in this campaign all happen to be Bifrost crew. Now any NPC can be spawned into combat
- **NPC dropdown grouped by source via `<optgroup>`:** `PLAYER NPCS` first (the player-assigned roster), then `DOSSIER · <AGENCY>` blocks alphabetically (one per NPC agency), then `DOSSIER · UNASSIGNED` for any dossiers without an agency FK
- The ADD PARTICIPANT block remains GM-gated, so dossiers are still GM-only at the participant-spawn surface

## v0.15.10
- **Player-picked specialisations on the attack form.** Each specialisation matching the auto-picked weapon skill on the actor's `Character.specialisations` / `NPC.specialisations` JSONField renders as a checkbox under the SKILL input (`☐ Pistols (+1)`, etc.). Ticking a box adds `+1` dice, and the LIVE TOTAL updates client-side in real-time as the player toggles. Unticked is the default; the attack pool ceiling printed by the breakdown is the *base* (no specs) — the player decides which specs are situationally applicable per shot
- **Server-side validation against pool inflation.** Each submitted `applied_specs` POST entry is matched (case-insensitively) against the actor's actual specialisations filtered by the resolved skill name. Names that aren't on the validated list are dropped silently — a tampered POST with arbitrary +1 stacks simply doesn't get the bonus, and there's no error to the user (the form-rendered checkboxes can never produce one). Duplicates are de-duped
- **Mooks have no specialisations.** Catalogue mook templates don't carry the `specialisations` field, so the helper short-circuits to `[]` and no checkbox row is rendered. Same for participants whose underlying Character / NPC FK has been `SET_NULL`'d
- **CombatLog payload now includes `applied_specs` (validated names) and `spec_bonus` (count).** The attack message appends `(+SPEC: name1, name2)` (or, when willpower is also spent, `(WP+3 | +SPEC: ...)`) so the timeline reads cleanly
- **Known limitation — spec list is computed at page render** based on the auto-picked skill. If the player overrides the SKILL `<input>`, the rendered specialisation list does NOT refresh until the page reloads. A v0.15.11+ improvement could be a JSON endpoint returning specialisations for an arbitrary skill name, called via `fetch` on the SKILL field's `blur` event
- New helper `_specialisations_for_skill(actor, skill_name)` in `combat/views.py`. `_actor_total_pool` gains an `applied_specialisations` keyword. `_attack_preview` returns two new fields: `specialisations` (list of names available on the resolved skill) and `spec_bonus` (always 0 in the preview — JS owns the live count)
- No schema changes, no migrations, no new dependencies

## v0.15.9
- **Live numeric attack pool preview** on every participant's attack form. The PREVIEW row now renders a server-side numeric breakdown — DEX/POOL + SKILL + WEAPON + WOUND + COND, with a separate LIVE TOTAL line that re-computes client-side as the GM modifier `<input>` changes. Mook breakdown collapses to MOOK POOL + WOUND + COND (no skill/weapon axis). The total is floored at zero so a heavily-debuffed attacker can't display a negative pool. New `_attack_preview` helper on `combat/views.py` and a per-attacker `p.attack_preview` annotation on `encounter_page`
- **Weapon skill auto-picked from weapon category.** New `WEAPON_CATEGORY_SKILL` map and `_weapon_skill_for(weapon_data)` helper: `firearm → Firearms`, `thrown → Athletics`, `melee → Weaponry`, `improvised → Weaponry`, unknown → `Weaponry`, unarmed (no equipped weapon) → `Brawl`. The SKILL `<input>` on the attack form now defaults to and placeholds the auto-picked value, with a "SKILL AUTO-PICKED FROM WEAPON CATEGORY (…). EDIT TO OVERRIDE." hint underneath. Field stays editable for narrative overrides (e.g. rifle butt as a club via Brawl)
- **Empty `weapon_skill` form value resolves server-side** to the auto-picked default before reaching `_actor_total_pool`. Explicit non-empty values pass through unchanged so a player typing "Brawl" with a rifle equipped gets the Brawl pool, not Firearms. The server is the source of truth — even a tampered POST with an empty `weapon_skill` rolls the right pool now
- **Willpower availability surfaced** above the attack form: `WP n/max — SPEND FOR +3 DICE` (or `— NONE TO SPEND` at zero). The spend-WP checkbox is now disabled when `willpower_current == 0` so a player can't tick it uselessly
- **No behavioral change to the actual attack roll** — the resolver math is bit-identical to v0.15.8. Purely UI/UX polish: players see the dice math before they pull the trigger, and don't have to remember which skill applies to which weapon category
- No schema changes, no migrations, no new dependencies

## v0.15.8
- **Players can now control their own characters in combat** — equip / cover / attack / dodge / full-defense / spend willpower / clear self-conditions / roll initiative for own character. The collapsible action panel on a player's own row, the inline × clear-condition buttons on its pills, and the per-row ROLL initiative button are all visible to a player on rows whose `Character.owner` matches the request user
- **PvP fully enabled at the player layer:** any character can attack any other participant when it's their turn. The `attack` view's existing self-target reject and active-participant check stay in place; faction is decorative (unchanged from v0.15.4)
- **GM-only actions remain GM-only:** encounter CRUD, participant add/remove, lifecycle (start/end), turn advance, roll-all initiative, clear initiative, and GM-imposed conditions (`stunned` / `blinded` / `grappled` / `incapacitated`)
- **Players cannot self-apply hard-incap conditions and cannot self-clear them.** `set_condition` now soft-rejects with a flash message when a non-superuser POSTs anything outside `{prone}`. `clear_condition` soft-rejects the same way for tags outside `{prone, defense_full, dodge_pending, dodging}`. Players can apply `prone` to themselves; the rest stay GM-imposed
- **Willpower direction guard:** players can only set willpower DOWN, not up. `adjust_willpower` flash-rejects a non-superuser POST that would raise the value — willpower restoration is the GM's call
- **`[YOU]` accent tag** highlights a player's own character row in the participants list (per-row, primary-glow styled). GMs do not see the tag — they control everyone, the highlight would be noise
- **Sub-strip text on /combat/ and encounter detail clarifies role.** The list page now reads "PERSONAL COMBAT — GM ONLY" for the GM and "PERSONAL COMBAT — PLAYER VIEW · TAKE TURNS / SPECTATE OTHERS" for players. The encounter detail kicker shows "PLAYER VIEW · CONTROL YOUR CHARACTER" when the user has at least one controllable participant; the GM gets no kicker; the defensive READ-ONLY · LIVE SPECTATOR fallback survives if reached
- **New decorator `_gm_or_owner()`** replaces `_gm_only` on the 10 player-permitted action views: `roll_initiative`, `equip_weapon`, `equip_armor`, `set_cover`, `set_condition`, `clear_condition`, `adjust_willpower`, `full_defense`, `dodge`, and `attack` (which uses `attacker_id` as the URL kwarg). Ownership is enforced server-side via the `Participant.character.owner` FK with a `select_related("character")` lookup so the gate doesn't N+1
- **Defense in depth:** the decorator handles ownership (hard 403); view bodies retain action-specific soft checks (active-turn for full-defense / attack, condition allow-list for set/clear, willpower-direction for adjust). Soft rejects redirect with `messages.error()` so players see a meaningful explanation rather than the bare clearance gate
- **Template gate model overhauled.** The binary `read_only` flag is replaced with two role-aware values: `is_gm` (page-level GM controls — encounter CRUD / lifecycle / ADD PARTICIPANT / × REMOVE) and `p.can_control` (per-row action panel + inline clear buttons + per-row ROLL). `has_any_control` drives the kicker. Both `participants` and `ordered_participants` are annotated server-side; the template stays declarative
- **WS consumer unchanged** — v0.15.7's superuser-or-character-participant gate already lets players receive live updates. **MCP unchanged** — combat actions stay GM-only via the bearer-token middleware
- No model or migration changes; no new dependencies. All ownership data already in place via `Participant.character → Character.owner`

## v0.15.7
- **Story-arc linking.** Encounters can now attach to a `gm_workspace.StoryIdea` via a new optional FK (`SET_NULL` on delete, `null=True, blank=True`). The link surfaces in three places: a STORY ARC column on `/combat/`, a deep-link badge in the encounter detail header (`STORY ARC: <title>` — links into `/gm/story-ideas/#<id>` for superusers, plain text for spectators), and a populated `<select>` in both the create and inline-edit forms with an empty `— NO STORY ARC —` first option. `_resolve_story_idea` helper centralises the lookup; blank string / "0" / unknown id all collapse to `None` so stale form posts can't 500
- **Player visibility — read-only spectator view.** Players whose `Character` is currently a `Participant` of an encounter can now load `/combat/` (filtered to their own encounters) and `/combat/<id>/` (read-only). Every GM action surface is gated behind a single `read_only` template flag: ADD PARTICIPANT block, EDIT / DELETE header buttons, EDIT form, ROLL ALL / CLEAR / START / NEXT TURN / END lifecycle buttons, per-row × REMOVE, the inline × clear-condition buttons on each pill, and the entire `<details class="part-actions">` panel of seven mini-forms. Read-only viewers still see name, kind, conditions, cover, MOD/wound chips, HP/WP counters, the initiative tracker, the live indicator, and the timeline — so they spectate the same state the GM mutates, just without action chrome. New `READ-ONLY · LIVE SPECTATOR VIEW` kicker line above the encounter title makes the mode obvious
- **Tightened WS consumer authorisation.** `combat/consumers.py` `EncounterConsumer.connect` now closes with code `4403` for any authenticated user who is neither superuser nor the owner of a `Character` participating in the requested encounter. The check uses the same `Participant.objects.filter(encounter_id=…, character__owner=user)` shape as the HTTP gate so WS visibility never widens the surface beyond the page
- **Conditional COMBAT nav link.** New `combat/templatetags/combat_tags.py` exposes `{% has_combat_visibility user %}` — returns True for superusers and for any authenticated user who has at least one Character in any encounter (one cheap EXISTS query per request). `base.html` uses it to render a top-level COMBAT link in the main nav rail next to RULES, in addition to the OPERATIONS dropdown's existing GM-only entry. The redundancy is intentional — superusers see both, players only see the rail link, anonymous users see nothing
- **11 new MCP tools (96 → 107).** Read + create + lifecycle coverage; **attack and condition manipulation deliberately stay in the web UI**, since combat actions need the GM at the keyboard. Tools: `list_encounters`, `get_encounter(encounter_id, log_limit=30)`, `create_encounter(title, scene_description="", location_text="", story_idea_id=None)`, `add_encounter_participant_character(encounter_id, character_id, faction="player")`, `add_encounter_participant_npc(encounter_id, npc_id, faction="hostile")`, `add_encounter_participant_template(encounter_id, template_name, faction="hostile")`, `remove_encounter_participant(encounter_id, participant_id)`, `start_encounter(encounter_id)`, `end_encounter(encounter_id)`, `roll_encounter_initiative(encounter_id)`, `next_encounter_turn(encounter_id)`. All wrapped in the same `try / except: logger.exception(...); return _error(str(e))` shape as the existing spacebattle tools
- **JSON API surface for combat.** Seven new endpoints under `/api/admin/combat/encounters/` authenticate via the existing `MCP_API_TOKEN` bearer middleware (same shape as the weapons / armor / cover / combat-npcs admin API) and return clean JSON dicts via the new `_serialize_encounter` / `_serialize_participant` / `_serialize_log_entry` helpers. Lifecycle transitions return 409 on state-drift (start on already-active, end on already-concluded, advance turn on non-active) so the MCP client can detect drift rather than silently no-op'ing. All `_log()` calls go through the same chokepoint as the web views so every API mutation also fans out via the WebSocket group
- **Migration `combat/0002_encounter_story_idea`** adds the optional FK. No data migration needed — existing rows null-default cleanly
- No new dependencies; all schema mutations isolated to the single new migration

## v0.15.6
- **Real-time fan-out via Channels.** Every `CombatLog` write now broadcasts a typed event to the `combat_<id>` Channels group. The hook lives in the `_log()` helper itself — every mutation already routes through it, so no per-endpoint plumbing is needed. Payload mirrors the log row: `encounter_id`, `sequence`, `round_number`, `action_type`, `message`, `data`, `timestamp`
- **Encounter page subscribes via WebSocket.** New 60-line vanilla-JS block at the bottom of `templates/combat/encounter.html` opens `/ws/combat/<id>/`, debounces incoming events (a single attack logs both `attack` and `health_change` — they collapse into one reload via a 250ms timer), and triggers `location.reload()`
- **LIVE / DISCONNECTED indicator** in the encounter header — green `● LIVE` on `onopen`, muted `○ DISCONNECTED` on `onclose`. Exponential-backoff auto-reconnect starting at 1s, capped at 30s — matches the comms WS pattern in `base.html`
- **UPDATE PENDING guard.** If the GM is mid-typing in an `INPUT` / `TEXTAREA` / `SELECT` when an event arrives, the reload is deferred and the indicator switches to amber `● UPDATE PENDING — RELOAD WHEN READY`. A `focusout` listener flushes the pending reload as soon as focus leaves the form, so unsaved input is never silently wiped
- **Defence-in-depth resilience.** The `broadcast_combat_event` helper in `combat/consumers.py` already swallows channel-layer exceptions; v0.15.6 wraps the call site in `_log()` with its own `try/except Exception: pass` so even a missing channel layer (e.g. running `manage.py shell` outside Daphne) cannot 500 a REST mutation
- **List page intentionally not WS-wired.** The GM is on the encounter detail page when running combat; real-time on `/combat/` is out of scope and would only add noise
- **All v0.15.5 action_types now broadcast** through the `_log()` chokepoint: `system`, `initiative`, `turn_advance`, `round_advance`, `attack`, `health_change`, `weapon_change`, `armor_change`, `cover_change`, `condition_set`, `condition_clear`, `willpower_change`, `full_defense`, `dodge`
- **Consumer is loose-auth on purpose.** Any authenticated user can subscribe to any encounter group in v0.15.6 — REST endpoints stay GM-only, so only GMs can produce events. Tightening visibility against `Encounter.participants` lands with v0.15.7 player-facing surfaces
- No schema changes, no new dependencies, no settings or ASGI touches — pure edits to `combat/views.py` and `templates/combat/encounter.html`

## v0.15.5
- **Wound penalties.** Every dice pool (attack and dodge) is now reduced by the WoD 2.0 wound penalty for the rightmost three filled health boxes — `−1 / −2 / −3` left → right. New `_wound_penalty` helper, surfaced as a small red `WP −N` chip on every participant row when non-zero
- **Damage track upgrade rule.** Refactored damage application into `_apply_damage(participant, amount, dtype)` honouring the WoD 2.0 ladder (B → L → A): empty boxes fill normally; once full, lethal overflow upgrades a bashing box per point, aggravated overflow upgrades a bashing then lethal box per point. Bashing overflow drops harmlessly. Log payload now carries `applied / upgrades / overflow` for the timeline
- **Auto-incapacitation.** When the target's total damage equals or exceeds `health_max` after a hit, an `incapacitated` tag is appended to `participant.conditions` and a separate `condition_set` log row fires. `_compute_defense` short-circuits to 0 for incapacitated participants
- **Conditions vocabulary.** Hardcoded `CONDITION_DEFS` for `prone` (def −2), `stunned` (atk −2 / def −2), `blinded` (atk −3 / def −2), `grappled` (atk −2 / def −2), `incapacitated` (sentinel −99 / locks out), `defense_full` (stance, doubles baseline def), `dodging:N` (stance, replaces def with rolled successes), `dodge_pending` (carry-tag for out-of-turn dodge cost). Conditions live as a list of strings on the existing `participant.conditions` JSONField — no schema change
- **Willpower spend on attack.** New `SPEND WP (+3 DICE, COSTS 1 WP)` checkbox on the ATTACK form — adds +3 to the pool and decrements `willpower_current` (clamped at 0; silent no-op when out). New `adjust_willpower` endpoint for manual GM tweaks (clamped 0..willpower_max). Log payload includes `spent_willpower` and `willpower_after`; message tags hits / misses with `(WP+3)` when spent
- **Full Defense stance.** `FULL DEFENSE` button on the active participant's row — appends `defense_full`, marks `acted_this_round=True` (eats the turn but does NOT advance the pointer), doubles the baseline defense pool until the next round
- **Dodge action.** `DODGE` button on every participant row (in or out of turn). Rolls `Dex + Athletics` (character / NPC) or `mook_defense` (mook), applies wound + condition modifiers to the pool, stores the successes as a `dodging:N` tag. `_compute_defense` substitutes `N` for the normal defense pool. Out-of-turn dodge tags `dodge_pending`; `next_turn` consumes that tag when the participant becomes active (marks them acted, strips the tag, logs a `system` row)
- **Defensive stances clear at round boundary.** `next_turn` now strips every `defense_full` and `dodging:*` tag across the encounter when the round rolls over, with a single `system` log row "Defensive stances cleared at round boundary."
- **UI surface.** Condition pills on every row (red for incapacitated, cyan for `defense_full` / `dodging:N` / `dodge_pending`, amber for ordinary statuses) with inline `×` clear buttons; `MOD` chip combining wound + condition attack modifier; `WP −N` wound chip; `WP n/max` willpower readout; new STANCE / ADD CONDITION / WILLPOWER sub-forms in the actions panel
- **New CombatLog action types:** `condition_set`, `condition_clear`, `willpower_change`, `full_defense`, `dodge`. Full vocabulary as of v0.15.5: `initiative`, `turn_advance`, `round_advance`, `system`, `attack`, `health_change`, `weapon_change`, `armor_change`, `cover_change`, `condition_set`, `condition_clear`, `willpower_change`, `full_defense`, `dodge`
- All five new endpoints CSRF-protected, GM-only, and reject non-POST. PvP still allowed — faction is decorative; nothing in v0.15.5 enforces faction restrictions
- No schema changes — every field used (`conditions`, `willpower_current`, `willpower_max`, `health_*`) was already on the v0.15.0 Participant model
- Real-time WebSocket fan-out still lands in v0.15.6

## v0.15.4
- **Attack actions during active encounters.** New per-row **ATTACK** form on the active participant — pick a target, optional skill (Firearms / Brawl / Weaponry — datalist autocomplete), and a free-form signed integer GM modifier. Server-rolled WoD 2.0: 8/9/10 successes, 10s explode and re-roll up to 5 levels deep (cap protects against the pathological all-tens streak). Pool is `Dex + skill + weapon dice modifier + GM modifier` for character / NPC, `mook_combat_pool + GM modifier` for mooks
- **PvP allowed.** Target picker shows every other participant in the encounter regardless of faction — faction is decorative, not enforced. The active-participant gate still applies (only the actor whose turn it is can attack)
- **Cover penalty model.** `light = −2` and `heavy = −4` subtract from the attacker's dice pool; `full` cover auto-blocks the shot — no roll, single `attack` log row with `outcome="blocked_by_cover"`. The math is one-sided so cover never double-counts by also bumping defense
- **Defense pool** for the target: `min(Dex, Wits) + Athletics` (character / NPC) or `mook_defense` (mook). `defense_override` pinned on the participant wins unconditionally. Same defensive `try/except` fallbacks as initiative — partial / legacy sheets never crash the resolver
- **Damage + armor.** Hit damage is `successes + weapon damage` (parsed from the catalogue's free-text `damage` string — leading digits + first `B`/`L`/`A` character). Armor mitigation reads `B/L` from the catalogue rating string for character / NPC or `mook_armor_rating` for mooks; aggravated bypasses armor entirely. Damage is applied to the matching health track, capped at `health_max`. Overflow is logged in the payload but **no track upgrade** (bashing → lethal → aggravated) is enforced — that lands in v0.15.5
- **Equip weapon / armor / cover from the catalogues** — three new sub-forms on every participant row, collapsed into a `+ ACTIONS` `<details>` panel so the participant list stays compact. Catalogue entries are *snapshotted* into `weapon_data` / `armor_data` / cover fields at equip time so a later catalogue edit does not retroactively rewrite the in-flight encounter. Cover entry name is optional — selecting one populates `cover_durability` + `cover_health` for the v0.14.65 cover-destruction track; freeform text is allowed
- **New CombatLog action types:** `attack`, `health_change`, `weapon_change`, `armor_change`, `cover_change`. A hit writes both an `attack` row (full resolution payload — pool, defense, cover penalty, dice, successes, raw damage, armor reduction, final damage, damage type, GM modifier, weapon name, weapon skill, overflow) and a separate `health_change` row so the timeline can be filtered down to damage-only events without re-parsing attack payloads. Misses and blocked-by-cover write a single `attack` row
- All four new endpoints CSRF-protected, GM-only, and reject non-POST with `HttpResponseNotAllowed(["POST"])`. Self-targeting and out-of-turn attacks are rejected with a flash message
- **Cover state pill** on every participant row — cyan for light, blue for heavy, purple for full — so the GM can read the board at a glance
- No schema or migration changes — every field used (`weapon_data`, `armor_data`, `cover_state`, `cover_entry_name`, `cover_durability`, `cover_health`, `defense_override`, `health_bashing` / `_lethal` / `_aggravated`, `mook_*`) was already in the v0.15.0 model
- **Still GM-only** — player-facing visibility and real-time fan-out land in v0.15.6

## v0.15.3
- **Initiative + turn advance.** Per-participant **ROLL** button, **ROLL ALL INITIATIVE** for unrolled participants in one pass, and **CLEAR INITIATIVE** to wipe rolls and revert an active encounter back to setup. Server-rolled via the `secrets` module — same crypto-quality randomness as the rest of the project's roll endpoints
- **WoD 2.0 model:** Character / NPC initiative is `Dexterity (finesse.physical) + Composure (resistance.social) + 1d10`; mooks roll `combat_pool / 2 + 1d10` (integer division). Partial / legacy sheets fall back to modifier `0` via defensive `try/except` rather than crashing
- **Tiebreak by participant id (lower first).** Deterministic and reproducible; `initiative_order` is rebuilt from scratch on every START so newly-added participants slot in cleanly
- **Encounter lifecycle endpoints.** `START ENCOUNTER` (gated on every participant having rolled — flashes the unrolled count via Django messages otherwise) transitions `setup → active`, sets `round_number=1`, points `active_participant_id` at the top of the order, stamps `started_at`. `NEXT TURN` advances the pointer; at end-of-order the round increments, `acted_this_round` resets across the board, and a `round_advance` row is logged. `END ENCOUNTER` transitions `active → concluded`, clears the active pointer, stamps `ended_at`, and redirects to the list
- **INITIATIVE TRACKER UI** on the encounter page — a new `.brackets` block above SCENE. Renders the round / status header, the action strip (state-dependent buttons), and an ordered roster (score desc, id asc, nulls last) with kind badges, score pills, per-row ROLL buttons (setup only), `ACTING NOW` pill on the current actor, and a muted `ACTED` indicator on participants who have already taken their turn this round
- Encounter list adds a **STARTED** column (`d M H:i` once kicked off, `—` while in setup) and downgrades the ROUND column to `—` outside of `active` status
- Stricter DELETE confirm wording on the encounter detail header
- All transitions logged with explicit action types: `initiative` (per-roll), `turn_advance`, `round_advance`, `system` (start / clear / end / batch summary)
- All POST endpoints CSRF-protected, GM-only, and reject non-POST with `HttpResponseNotAllowed(["POST"])`
- **No real-time fan-out yet** — WebSocket broadcast lands in v0.15.6
- No schema or migration changes; all the relevant fields landed in v0.15.0 (`status`, `round_number`, `active_participant_id`, `initiative_order`, `started_at`, `ended_at`, `initiative_score`, `initiative_roll`, `acted_this_round`, `surprise_immune`)

## v0.15.2
- **GM-only Encounter CRUD at `/combat/`.** New encounter list page (with collapsible "+ NEW ENCOUNTER" form) and per-encounter detail page covering header / scene / participants / add-participant / timeline. Status pills map `setup → s-standby`, `active → s-active`, `concluded → s-dormant`. EDIT toggles an inline metadata form; DELETE is `confirm()`-guarded
- Three participant spawn sources: **CHARACTER** (player sheet — `health_max = size + Stamina`, `willpower_max = Resolve + Composure`, with KeyError fallbacks `7` / `0`); **NPC** (full NPC dossiers, `is_npc_dossier=False`); **TEMPLATE** (Combat NPC catalogue entry snapshotted as a mook). Templates are grouped by category in `<optgroup>`s in the spawn form
- **Snapshot model:** catalogue entries are denormalised into the Participant row at spawn time (`mook_combat_pool`, `mook_defense`, `mook_armor_rating`, `weapon_name`, `notes`, `health_max`). Later catalogue edits do **not** retroactively mutate active encounters — defensive `int()` casts (`_safe_int`) handle the all-strings catalogue shape gracefully
- **Read-only timeline.** Every CRUD operation appends a `CombatLog` row with `action_type="system"` and a monotonic per-encounter sequence (allocated through the `_next_sequence` helper so the unique `(encounter, sequence)` constraint can never break). Encounter creation seeds sequence 1 with "Encounter created."
- New `/combat/` link in the OPERATIONS dropdown (under GM, superuser-only)
- All POST views are CSRF-protected and reject non-POST with `HttpResponseNotAllowed(["POST"])`. All views (GET + POST) return `HttpResponseForbidden("ACCESS DENIED.")` for non-superusers
- **No rolls / initiative / real-time fan-out yet** — those land in v0.15.3+ (attacks + damage), v0.15.4 (full attack loop), v0.15.5 (WebSocket fan-out)
- No schema changes; phase-0 models from v0.15.0 are unchanged

## v0.15.1
- New **COMBAT NPC TEMPLATES** catalogue — stock combat-ready stat blocks the GM can spawn as mook participants in encounters. 15 seed entries across 5 categories: **GUARD** (Generic Guard, Building Security, Bouncer), **RAZOR** (Street Razor, Cyber-Razor, Pit Fighter), **CORPORATE** (Corp Sec Officer, Executive Bodyguard, Black Ops Operator), **CULTIST** (Initiate, Adept, Champion), **DRONE / NON-HUMAN** (Sentry Drone, Combat Drone, Guard Dog). The drone category covers both autonomous machines and biological attack animals — mechanically they fight the same way (no morale, no intimidation, attack on command)
- Each entry: `name`, `category`, `combat_pool` (attack dice pool), `defense` (passive defense), `health_max` (total HP boxes), `armor_rating` (B/L subtraction or `—`), `weapon` (free-text or matches the weapons catalogue), `notes` (free-text flavor / behavioral notes)
- New **`/settings/ → COMBAT → Combat NPCs`** structured editor mirroring the weapons / armor / cover pattern (row-based table per category, `＋ ADD COMBAT NPC` per category, delete-per-row, inline rename)
- Combat reference at `/rules/combat/` now renders a **STOCK ADVERSARIES** section as five tables (one per non-empty category) below the armor catalogue. Columns: NAME / POOL / DEF / HP / ARMOR / WEAPON / NOTES. Empty categories are hidden
- Two new admin-only API endpoints (`/api/admin/combat-npcs/` list+create, `/api/admin/combat-npcs/<name>/` get+put+delete) and five MCP tools (`list_combat_npcs`, `get_combat_npc`, `create_combat_npc`, `update_combat_npc`, `delete_combat_npc`) so Claude can manage the catalogue without the admin UI. Names are URL-encoded so spaces / hyphens (e.g. `Cyber-Razor`, `Corp Sec Officer`) work transparently
- Migration `exodus/0021_sitesettings_combat_npcs` adds the `SiteSettings.combat_npcs` JSONField and seeds the default catalogue on first apply
- v0.15.2 will let you spawn these templates into encounters as participants (the encounter CRUD + initiative pass)

## v0.15.0
- **Combat module — Phase 0 skeleton.** New `combat/` Django app with `Encounter`, `Participant`, `CombatLog` models, migration `combat/0001_initial`, admin registration, placeholder `/combat/` and `/combat/<id>/` pages (GM-only), and the WebSocket consumer skeleton (`combat_<id>` group, `broadcast_combat_event` helper). The phase-0 release is internal — encounter CRUD ships in v0.15.1, real participants + initiative in v0.15.2, attacks + damage in v0.15.3, full attack loop in v0.15.4, real-time fan-out in v0.15.5, MCP + GM workspace integration in v0.15.6
- Combat models reference the existing weapons / armor / cover catalogues (`SiteSettings`) and link to `Character` / `NPC` via `SET_NULL` so deleting an actor mid-encounter snapshots their `name` rather than corrupting the log
- Adopted the spacebattle real-time pattern: per-encounter Channels group, broadcast helper that swallows Redis outages so REST still works

## v0.14.65
- New **COVER & CONCEALMENT** rules section in the combat reference at `/rules/combat/`. Distinguishes cover (stops bullets) from concealment (stops sight). Tiered: LIGHT (−2), HEAVY (−4), FULL (cannot target). Sub-sections cover entering, pop-up fire, blind fire, moving between cover, autofire suppression, and rules for destroying cover (Durability + Health). Footnote on heavy ordnance / explosives bypassing cover
- Cover destruction table is now **driven by the editable cover catalogue** instead of hardcoded
- New `SiteSettings.cover` JSONField with seeded defaults across the three tiers: wooden chair / drywall / vehicle door (light); engine block / sandbag / brick wall (heavy); concrete wall / reinforced bulkhead (full)
- New **`/settings/ → COMBAT → Cover`** structured editor matching the weapons/armor pattern (rows per tier with NAME / DURABILITY / HEALTH / NOTES + delete-per-row + ＋ ADD COVER per tier)
- Two new admin-only API endpoints (`/api/admin/cover/` list+create, `/api/admin/cover/<name>/` get+put+delete) and five MCP tools (`list_cover`, `get_cover`, `create_cover`, `update_cover`, `delete_cover`)
- Migration `exodus/0020_sitesettings_cover` adds the field and seeds the default catalogue

## v0.14.64
- New **ARMOR** catalogue mirroring the weapons setup. Stored on `SiteSettings.armor` with seeded defaults across four categories: **LIGHT** (Reinforced Coat, Kevlar Vest, Tactical Vest), **MEDIUM** (Riot Gear, Plate Carrier, EOD Suit), **HEAVY** (Full Ballistic, Combat Plate, Powered Exo-Frame), **VACUUM** (EVA Suit, Hardsuit, Industrial Hardsuit)
- Each armor entry: `name`, `category`, `rating` (B/L subtraction, e.g. `1/2`), `str_min` (Strength minimum, `—` if none), `penalty` (combined Defense/Speed/Init negatives), and free-text `notes`
- New **`/settings/ → COMBAT → Armor`** structured editor (row-based table per category, `＋ ADD ARMOR` button per category, delete button per row)
- Combat reference at `/rules/combat/` now renders an **ARMOR CATALOGUE** section as four tables (one per category) below the weapons catalogue
- Two new admin-only API endpoints (`/api/admin/armor/` list+create, `/api/admin/armor/<name>/` get+put+delete) and five MCP tools (`list_armor`, `get_armor`, `create_armor`, `update_armor`, `delete_armor`) so Claude can manage the catalogue without the admin UI
- Migration `exodus/0019_sitesettings_armor` adds the field and seeds the default catalogue on first apply

## v0.14.63
- Two new admin-only API endpoints for the weapons catalogue:
  - `GET /api/admin/weapons/` — list all
  - `POST /api/admin/weapons/` — create new (409 on duplicate name)
  - `GET /api/admin/weapons/<name>/` — fetch one (case-insensitive name)
  - `PUT /api/admin/weapons/<name>/` — partial update (rename, change stats)
  - `DELETE /api/admin/weapons/<name>/` — remove
- Five new MCP tools wrapping the endpoints (`list_weapons`, `get_weapon`, `create_weapon`, `update_weapon`, `delete_weapon`) so Claude can manage the catalogue without the admin UI. Names are URL-encoded so spaces and parentheses (e.g. `Taser (Contact)`) work transparently

## v0.14.62
- **Weapons now carry stats.** Each entry in the catalogue gets `damage` (e.g. `1L`, `2B`, `4L close / 2L long`), `range` (`—` for melee, `S/M/L m` for ranged, `Str ×3/×6/×12 m` for thrown), `capacity` (`12+1`, `30`, `1 cartridge`, `—`), and free-text `notes`. Default seed updated with WoD 2.0–style stats for all 20 starter weapons
- Settings editor at `/settings/ → COMBAT → Weapons` is now a structured **row-based table per category** instead of a flat textarea. Each row has columns NAME / DAMAGE / RANGE / CAPACITY / NOTES + a delete button. Each category card has a `＋ ADD WEAPON` button to append a new row
- The combat reference at `/rules/combat/` now renders the **live weapons catalogue** as four tables (one per category) at the bottom of the page. Edits saved in `/settings/` reflect on next page load. Empty categories are hidden
- Migration `exodus/0018_weapons_with_stats` upgrades any legacy name-only entries (from v0.14.61) to the new enriched schema. Custom user-edited weapons with stats already populated are preserved untouched

## v0.14.61
- New **WEAPONS** catalogue under `/settings/ → COMBAT → Weapons`. Four textareas, one per category (MELEE / IMPROVISED / FIREARM / THROWN); one weapon name per line. Saved as a flat list of `{name, category}` dicts on `SiteSettings.weapons`
- Migration `exodus/0017_sitesettings_weapons` adds the field with a default catalogue seeded on first apply: knuckle buster, knife, baton, taser (contact); chair, bottle, phone book, hammer; hand gun, large hand gun, sub machine gun, assault rifle, DMR, shotgun, twin-barrel shotgun, auto shotgun, scoped rifle, taser (cartridge); throwing knife, throwing axe. The two "taser" entries are disambiguated as melee (contact) vs firearm (cartridge)
- Each category card shows a one-line cue for the WoD 2.0 attack pool that applies (e.g., MELEE → Strength + Brawl/Weaponry; FIREARM → Dexterity + Firearms; etc.) so adding a weapon is unambiguous about which dice pool it'll use

## v0.14.60
- Combat reference subtitle drops the `WoD 2.0 — ` prefix; reads cleanly as `POOL = ATTRIBUTE + SKILL ± MODIFIERS · 8+ SUCCESS · 10-AGAIN · NET DAMAGE = SUCCESSES − ARMOR`

## v0.14.59
- New **COMBAT** quick-reference page in the RULES section at `/rules/combat/`. Single-screen WoD 2.0 personal-combat cheat sheet covering: round structure (initiative + turn + end-of-round), attack pools (unarmed / melee / improvised / thrown / firearm / grapple), defense + dodge + armor + damage, health track + wound penalties + healing rates, common modifiers (cover / concealment / aiming / burst-fire / called-shots / movement / specialisations / willpower), and free-action examples
- RULES hub at `/rules/` now shows three cards: MERITS · PULLING STRINGS · COMBAT
- Footer notes that ship-to-ship combat lives under the STARSHIPS / BATTLES subsystems

## v0.14.58
- New **SPECIALISATIONS** multi-select in the project dice-pool config — pick one or more of the assigned character's specialisations and each match adds **+1 die** to the project roll (standard WoD 2.0 specialisation bonus). Sits next to the existing MERITS and PULLING STRINGS pickers
- Specialisation labels render as `<skill>: <name>` (e.g., `Investigation: Forensics`) so it's clear which sub-category applies. Multiple specialisations can stack
- Roll breakdown now shows specialisation rows as `<skill>: <name> +1` in the dice-pool detail
- Stored on `project.dicePoolConfig.matchingSpecialisations` (list of specialisation names). Server-side computation in `_compute_project_dice_pool`; serializer now exposes `specialisations` per character in `assignableCharacters`

## v0.14.57
- Fix: the council page (`/agencies/council/`) was keyed to a hardcoded purple accent (`#a855f7`) instead of the palette token, so it read as off-theme even after the clearance-gate rollout. Council borders, badges, filter pills, and vote tags now follow `var(--c-primary)` and respect palette flips in `/settings/ → THEME`. Abstain-vote color moved off purple to a neutral grey so it doesn't clash with whichever palette is active

## v0.14.56
- Renamed `CLEARANCE GATE` to **`THEME`** in `/settings/` — both the sidebar group label and the section header. The settings now read more accurately, since palette + clock timezone propagate to the authenticated app, not just the login splash. Description copy updated to reflect the broader scope

## v0.14.55
- New **CLOCK** section in `/settings/ → CLEARANCE GATE → TWEAKS` with a TIMEZONE selector that drives the header-strip clock. Defaults to UTC; choices include UTC + 13 common IANA zones (Copenhagen / Stockholm / Berlin / Paris / London / Helsinki / NY / Chicago / Denver / LA / Tokyo / Shanghai / Sydney). Clock label shows the live abbreviation (CET / CEST / EST / EDT / etc.) — switches automatically across DST boundaries
- Stored as `tweaks.timezone` on `SiteSettings`. Server-side validation against `zoneinfo.available_timezones()` so a malformed POST can't break the JS clock
- Login splash always shows UTC regardless of the setting (the splash is its own surface and stays consistent across sessions)

## v0.14.54
- Fix: multi-line Django `{# ... #}` comments were leaking through to the page in five templates (profile, login, register, briefs, site settings) — Django comment syntax `{# #}` is **single-line only**, multi-line blocks are passed through to the renderer as raw text. This was the unrendered ASCII-divider blocks visible at the top of `/accounts/profile/` (and similar). All five templates converted to `{% comment %}{% endcomment %}` blocks
- Per the existing project memory `feedback_django_template_comments.md`: this is a known footgun for agent-authored templates — do not use multi-line `{# #}` in this codebase

## v0.14.53
- New **OPERATIONS** dropdown in the top subsystem rail consolidates the admin links — `SETTINGS`, `ADMIN`, `GM` (the last only for superusers). Clicking the toggle reveals a square-cornered, accent-glow dropdown panel anchored to the right of the rail. Caret rotates 180° when open, click-outside or `Escape` closes it
- Three flat staff/superuser links collapse into one menu item, leaving the rail visually leaner

## v0.14.52
- Top subsystem nav rail now aligns to the right (`justify-content: flex-end`) instead of the left

## v0.14.51
- New **RULES** section consolidating the merit and pulling-strings catalogues. Hub at `/rules/` shows two cards (MERITS / PULLING STRINGS) inside a bracket-frame card. The standalone catalogues now live at `/rules/merits/` and `/rules/pulling-strings/`, with the old `/merits/` and `/pulling-strings/` URLs kept as silent aliases so existing bookmarks keep working
- Top nav simplified: the two flat links (`PULL STRINGS` + `MERITS`) become a single `RULES` link

## v0.14.50
- Fix: the login roster was showing `__SYSTEM__` twice when a real Django user account named `__system__` (or `system`) existed in the database — the real burned user and the always-on synthetic row collided. The roster now defensively excludes any real user whose username matches the synthetic sentinel, so only the always-on `CRAWLING` row appears

## v0.14.49
- Three new admin-only API endpoints for user profile management:
  - `GET /accounts/api/admin/users/` — list all users with profile + activity status
  - `GET /accounts/api/admin/users/<username>/` — single user's profile
  - `POST /accounts/api/admin/users/<username>/set-active/` — burn / un-burn (set `is_active`)
- Each user payload includes `username`, `isSuperuser`, `isActive`, `email`, `dateJoined`, `lastLogin`, `lastActivity`, `secondsSinceActivity`, `activityStatus` (ACTIVE / STANDBY / DORMANT / CRAWLING / INACTIVE / BURNED), `burned` flag, `characterName`, `characterClass`, `hasAvatar`
- Four new MCP tools wrapping the endpoints (`list_user_profiles`, `get_user_profile`, `set_user_active`, `set_user_last_activity`) so Claude can monitor + manage activity without the admin UI

## v0.14.48
- New `CRAWLING` status (muted ocher `#8a7656`) added to the login roster ladder. Sort order is now ACTIVE → STANDBY → DORMANT → **CRAWLING** → INACTIVE → BURNED
- Synthetic `__SYSTEM__` row always present on the roster — `CRAWLING` status, `SYSTEMS SECURITY` node, `ALWAYS` uplink. The in-fiction systems-security daemon that never logs off but never quite gets full bandwidth either. Excluded from the active-count badge (it's not a real human)

## v0.14.47
- The login roster now shows **`BURNED`** for users with `User.is_active=False` (operative left the group, kept on the roster for historical record). Sort order extended: ACTIVE → STANDBY → DORMANT → INACTIVE → **BURNED**. Status pill renders red via the existing `.s-burned` class
- `LastActivityMiddleware._maybe_logout_inactive` now also kicks out users whose `is_active` has been cleared, even if their session cookie is still valid. Belt-and-braces: `is_active=False` already blocks fresh logins; this also closes the existing session on their next request
- To mark a player as burned: visit `/admin/auth/user/`, click their username, uncheck **Active**, save. They'll show as `BURNED` on the next login page load and get force-logged-out on their next site request

## v0.14.46
- **Wave 5 of the clearance-gate aesthetic rollout — polish.** Adds the utility classes that Waves 2–4 agents repeatedly improvised inline. Future template work picks them up automatically; existing inline styles keep working until refactored
- New utility classes in `foundation.css`:
  - `.btn-cyber.sm` / `.btn-cyber.tiny` (and `.btn-primary.sm` / `.tiny`) — small button variants for inline rows and tag clouds
  - `.btn-ghost` — transparent secondary button for back-links and inline cancels
  - `.crumb` — `< BACK` breadcrumb primitive with auto `<` glyph
  - `.seg` + `.seg-btn` + `.seg-btn.active` — segmented control / tab row primitive
  - `.rail-item` + `.rail-item.active` — sidebar / channel list / file list current-item pattern (GM workspace, comms threads, settings sidebar already use this shape)
  - `.toggle-row` — checkbox + label + status-pill row pattern with palette-tinted accent
  - `.block-head.danger` — color-variant for danger-themed sections (BIOSIGN MONITOR, ADMIN PANEL, COMPROMISED) that tints bullet + h3 + divider line in one hop
  - `.brackets-tight` — smaller bracket-frame variant for nested authority cards
- New token `--c-danger-soft: rgba(255, 77, 94, 0.08)` for danger card backgrounds (replaces several hardcoded `rgba(239, 68, 68, ...)` literals)
- **Clearance-gate rollout complete.** Login, all hub/list pages, agency sheet (6 component files), character sheet, NPCs, comms, council, GM workspace, site settings, all maps, all battles, starships — every authenticated surface now reads as one product with the login screen. Five palettes (EMERALD/AMBER/ICE/BLOOD/BONE), three backdrops (login-only), tweaks tab in `/settings/`, light-theme support, square corners, JetBrains Mono + VT323

## v0.14.45
- **Wave 4 of the clearance-gate aesthetic rollout — maps, battles, settings, starships.** 10 templates restyled across three parallel agents on disjoint files. Canvas, Three.js, Leaflet, and SVG terrain content untouched per spec — chrome-only restyle around them
- Site settings (`site_settings.html`, ~1900L → 2054L): outer bracket frame around the whole shell, sidebar gets the rail-item active-pattern matching GM workspace, **17 `.block-head` section markers** (Game Date, Comms Lock, Map Visibility, Council, Nav Labels, Base Access, Clearance Gate / TWEAKS, City Maps, Star Map Config, Seed Star Systems, Starships, Ship Types, Module Sections, Ship Modules, View As Player, Transfer Player, Sidebar group), **14 status pills** for ENABLED/DISABLED/LOCKED/OPEN/UNLOCKED states. New TWEAKS scope note clarifies that palette propagates to the authenticated app via `<html data-palette>`
- Star map (`starmap/demo.html`, `citymap.html`) and world map (`agencies/world_map.html`): bracket frames around the canvas/Leaflet container, side panels get `.block-head` per section. Three.js scene setup, Leaflet GeoJSON layers, and `--map-*` tokens **not touched**
- Base config (`agencies/base_config.html`): bracket frame, custom `SectionPanel` `.block-head` directly on the collapse `<button>` with bullet/title/line/badge (avoids invalid HTML nesting)
- Spacebattle (`battle.html`, `list.html`, `map_editor.html`, `maps_list.html`, `_terrain_render.html`): bracket frames + 10 `.block-head` blocks (turn order, battle map, unit details, terrain palette, etc.). Status pills dynamically map participant.status → s-active (engaged/active), s-burned (destroyed), s-inactive (withdrawn), s-dormant (waiting). Hex-grid canvas drawing, ship-token rendering, SVG terrain rendering **not touched**. `_terrain_render.html` is pure canvas helpers — no chrome to restyle, left alone
- Starships (`starships/page.html`): bracket frame, 6 `.block-head` (Classes / Ships / Weapons / Shields / Batteries / Chassis), ship-status pill maps active → s-active, under_construction → s-standby, damaged → s-burned, in_dock → s-dormant, decommissioned/lost → s-inactive
- Total Wave 4: ~10 templates, +500 net LOC, 7 brackets, 35 block-heads, 21 status pills, ~24 `borderRadius` zeroings

## v0.14.44
- New admin-only endpoint `POST /accounts/api/admin/set-last-activity/` for bulk-setting `UserProfile.last_activity` timestamps. Body: `{"users": "all_non_superuser" | ["username1", ...], "timestamp": "ISO-8601"}`. Useful for testing the roster status pills (drift users into ACTIVE / STANDBY / DORMANT / INACTIVE bands without waiting for real time to pass)

## v0.14.43
- **Wave 3 of the clearance-gate aesthetic rollout — heavy authority surfaces.** 10 React-via-Babel templates restyled across four parallel agents on disjoint files
- **Agency sheet** (Wave 3A): 6 component files (`_app`, `_core_modules`, `_projects`, `_table_ftl`, `_changes`, `_bases`). 1 bracket-frame on the agency header authority card, 20 `.block-head` section markers, 17 status pills (hidden, XP, read-only, council statuses, change requests, project completes, base hidden), 122 `borderRadius` zeroings. Hooks (`useSectionSave`, `useBaseSectionSave`, `useProjectActionFetch`) and conflict-banner logic untouched
- **Character sheet** (Wave 3B): editable `templates/characters/sheet.html` (2365L). 1 bracket frame on HeaderModule with kicker/title/sub above the editable form, 13 `.block-head` section markers (Attributes, Skills, Specialisations, Derived, Pulling Strings, Merits, Experience with `[N XP REMAINING]` badge, Biosign Monitor, Inventory, Dossier, Classified Notes, Dice Roller, Flaws), 2 status pills, 20 `borderRadius` zeroings. StatDots / health track / mental load / EKG / cybernetics tracker preserved
- **NPCs** (Wave 3C): list + detail. List page in bracket frame with state pills (active/leave/missing/deceased → `s-active`/`s-standby`/`s-burned`/`s-inactive`). Detail page in bracket frame with 17 `.block-head` section markers and 10 status pills (state, hidden-section redactions, BIOSIGN MONITOR, ADMIN PANEL, COMPROMISED indicators), 14 `borderRadius` zeroings
- **Comms** (Wave 3D): `templates/comms/index.html` (1833L). Page in bracket frame, 5 `.block-head` panels (CHANNELS with unread badge, ThreadView with msg count, MemberManager, NewThreadModal, INTERCEPTED), 4 status pills (OWNER, ATTACHED file chip, system-message bubble, intercepted thread wrapper), `.field-wrap` compose row with `>` prompt + accent caret + textarea, pulsing `.dot` for unread. WebSocket logic, typing indicator, message edit/delete, file-attachment thumbnail untouched. CyberTerminal overlay kept its retro green-CRT aesthetic
- Total Wave 3: ~10 templates, +89 LOC net (counts vary because some chrome wraps replace existing structure 1:1), ~150 `borderRadius` zeroings, 30 status pills, 35 block-heads, 4 bracket frames

## v0.14.42
- New `UserProfile` admin registration at `/admin/accounts/userprofile/` — see every user's `last_activity` timestamp, computed status pill (ACTIVE / STANDBY / DORMANT / INACTIVE matching the login roster), and "since" delta. Also surfaces the same status column on the standard `/admin/auth/user/` list, with the profile (incl. avatar + last_activity) inlined on each user's edit page

## v0.14.41
- **Wave 2 of the clearance-gate aesthetic rollout — hub & list surfaces.** 17 templates restyled across two parallel agents on disjoint file sets. ~22 bracket-frame cards, ~35 `.block-head` section markers, ~22 `.status-pill` indicators added. Every list / hub / authority page now reads native to the new aesthetic
- News (`list.html`, `detail.html`) — DISPATCH surfaces with bracket-frame cards, `.kicker` / `.title` / `.sub` display heads, dispatch-count badges. Visibility tags converted to status pills (PUBLIC → `s-active`, EYES ONLY → `s-standby`, HIDDEN → `s-burned`)
- Profile (`accounts/profile.html`) — three bracket cards (identity, avatar, passphrase), `.field` form primitives with `>` prompt glyphs and accent-on-focus carets, `s-active` ACTIVE badge
- List pages — agencies, characters, pulling-strings, merits, global flaws, FTL projects all wrapped in bracket frames with `.kicker` / `.title` / `.sub` heads and section count badges
- Read-only character viewer (`characters/view.html`) — full bracket card with 10 `.block-head` section markers (Attributes, Skills, Specialisations, Derived, Biosign Monitor with pulsing red pill, Pulling Strings, Inventory, Dossier, Dice Roller, Merits, Flaws). READ-ONLY pill at the top
- Council (`agencies/council.html`, `council_charter.html`) — UIC governance surface gets two bracket cards (members + items registry), 6 status pills for vote results (PASSED → `s-active`, REJECTED → `s-burned`, PENDING → `s-standby`, etc.), CHARTER block-head on the charter editor
- GM Workspace (`workspace.html`, `timeline.html`, `campaign_log.html`, `briefs.html`, `_sidebar.html`) — full splash treatment via `body.surface-splash` (vignette + heavier scanlines). Bracket shells, `.block-head` per tool, type pills (story-idea SHARED → `s-active`, PINNED → `s-standby`; timeline session → `s-active`, plot → `s-standby`, world → `s-burned`, note → `s-inactive`). Sidebar gets a `.block-head` group label and accent-glow active-rail item
- Square corners enforced; hardcoded color literals (`#fff`, `#a855f7`, etc.) replaced with palette-token references where semantic meaning was clear. Round avatars (`border-radius: 50%`) preserved
- Surfaces still pending Waves 3–4: agency sheet React modules, character editor sheet, NPCs detail/list, comms, settings tabs, maps, battles. Chrome inherits via Wave 1; surface-level treatment lands next

## v0.14.40
- **Wave 1 of the clearance-gate aesthetic rollout — shared chrome.** The rest of the project now inherits the login surface's terminal look automatically. EMERALD palette, JetBrains Mono + VT323 typography, square corners everywhere, dark void background, light scanlines overlay
- Re-tokenised `static/css/foundation.css`: new canonical `--c-primary / --c-dim / --c-glow / --c-soft / --ink / --ink-dim / --ink-mute / --bg / --font-mono / --font-display` tokens. Legacy `--accent-primary / --bg-dark / --text-primary` etc. now alias to the new tokens, so existing inline styles in JSX components keep working and pick up the new palette automatically (~hundreds of usages reflowed in one shot)
- New chrome utility classes available globally: `.brackets`, `.bk` corner pieces, `.strip` / `.foot` header & footer rails, `.block-head` section header pattern, `.status-pill` with `.s-active / .s-standby / .s-dormant / .s-burned / .s-inactive`, `.kicker / .title / .sub`, `.field` form primitives, `.scanlines / .vignette / .crt-curve` overlay layers
- `templates/base.html` rewritten: replaces the two-row nav with a clearance-gate-style **header strip** (pulsing dot + agency-name + EXODUS + your codename left; SES + OPS + UTC clock + BUILD right) and a **footer strip** (next session + node + build + ⏎ NAV). Live UTC clock updates every second. Light scanlines overlay always on (alpha lowered from login's 0.18 to 0.08); vignette + CRT curve are opt-in via `body.surface-splash`
- `tweaks.palette` from `/settings/` now propagates to the authenticated app via `<html data-palette="...">`. Switch palette in settings → both login and dashboard re-skin on next page load. Other tweaks (scanlines, vignette, backdrop, code-rain) remain login-cinematic-only as designed
- New context processors: `tweaks` (exposes the SiteSettings tweaks JSON) and `session_chrome` (computes codename + session-id + ops-online count, with a 30s in-process cache on the OPS counter so the strip header doesn't add a per-request DB query)
- Light-theme palette overrides extended for every palette so AMBER/ICE/BLOOD/BONE remain readable in light mode (each gets a darker variant of the accent for light backgrounds). Scanlines hide automatically in light mode
- Surfaces NOT touched in this wave: agency sheet React components, character sheet, NPCs, comms, news, settings, maps, battles. Those are Waves 2–4

## v0.14.39
- The **ACTIVE ROSTER** panel on `/login/` now shows real users instead of the fake operatives. CODENAME = the user's first character name (or `GM` for superusers); NODE = character class (FIXER / SOLDIER / SCIENCE / ENGINEER / AI), or `DIRECTOR` for the GM; UPLINK = compact "time since last activity" (`MM:SS` within the hour, `HH:MM` within the day, `Nd Hh` beyond, `—` for never). Status badge derived from the v0.14.38 `last_activity` timestamp per the spec
- Status thresholds: `ACTIVE` within 2 hours, `STANDBY` within 4 hours, `DORMANT` within 2 days, `INACTIVE` thereafter (or never seen). Roster is sorted ACTIVE → STANDBY → DORMANT → INACTIVE then alphabetically by codename. The `N / M` badge in the header now reflects "active count / total"
- New `s-inactive` row style — desaturated grey, 55% opacity row + 75% opacity pill — so inactive operatives read as cold but not alarming (the original BURNED red is reserved for actual compromise scenarios)
- **Auto-logout for inactive users**: a player whose `last_activity` is older than 2 days has their session invalidated on their next request. They reappear on the roster as `INACTIVE` and have to re-authenticate at the gate. Implemented in `LastActivityMiddleware._maybe_logout_inactive` in the request phase

## v0.14.38
- New **`UserProfile.last_activity`** timestamp field, updated on every authenticated HTTP request via a new `LastActivityMiddleware`. Used for site-activity monitoring (e.g., "who has been on the site recently"). Each new action overwrites the previous timestamp
- Implementation runs in the response phase (no added request latency), uses `QuerySet.update()` to touch only the timestamp column, and is **debounced to once per 30 seconds per user** so a player rapidly clicking, typing, or polling doesn't hammer the DB
- Skipped silently for: anonymous users, MCP API requests (Bearer-token auth — that's tooling, not a human action), and static / media file paths. Errors are logged but never 500 the page
- Migration `accounts/0002_userprofile_last_activity` adds the field with `db_index=True` so monitoring queries (e.g., "list users active in the last hour") are cheap

## v0.14.37
- Fix: clearance-gate kicker on `/login/` now reads the **DIRECTORATE** value from `/settings/ → CLEARANCE GATE → TWEAKS` instead of the hardcoded `"DIRECTORATE OMEGA"`. Both the JS-on render and the no-JS fallback now show `DIRECTORATE {{ agency_name }}  //  PROJECT {{ op_codename }}`
- Fix: granted-dossier copy in the post-login cinematic. Previously rendered `PROJECT:   PROJECT OMEGA-7` (duplicate "PROJECT" word). Now: `CLEARANCE: TIER-3 // DIRECTORATE <agency_name>` and `PROJECT:   <op_codename>`

## v0.14.36
- Branding labels in `/settings/` → `CLEARANCE GATE → TWEAKS` renamed: `AGENCY NAME` → `DIRECTORATE`, `OP CODENAME` → `PROJECT`. Matches the on-screen kicker copy "DIRECTORATE OMEGA // PROJECT EXODUS" so the field labels read as the operator's directorate and project assignment, not the brand. The underlying `tweaks` JSON keys (`agency_name`, `op_codename`) are unchanged — no migration required, existing values preserved

## v0.14.35
- New **clearance-gate login surface** at `/login/` and `/register/` — terminal-aesthetic multi-stage flow (boot screen → login → authing cinematic → granted/denied splash). Animated agency-map background with continent point-in-poly dot grid, radar sweep, connection arcs, focal-node crosshair, and 14 fixed operative nodes; alternative code-rain backdrop with selectable glyph set (Katakana / Hex / Binary / ASCII)
- Login submit is AJAX: the 3.3-second handshake cinematic plays AFTER the server confirms credentials, not before — the `<form method="POST">` fallback still works without JS for graceful degradation. The legacy 302-redirect path is unchanged
- 3 failed attempts trigger a client-side 30-second lockout with a live countdown banner; petition form (request new clearance) maps to the existing `/register/` flow
- Implemented in **vanilla ES2017+ vanilla JS + canvas**, not Babel-standalone, so the unauthenticated login surface stays light. Loads JetBrains Mono + VT323 from Google Fonts. Five palettes (EMERALD / AMBER / ICE / BLOOD / BONE), three backdrops (OPS_MAP / CODE_RAIN / PLAIN), optional scanlines / vignette / side telemetry rails
- New **CLEARANCE GATE → TWEAKS** tab in `/settings/` (admin-only) configures the login surface persistently: palette, backdrop, map intensity, radar / nodes toggles, code-rain glyphs / density / speed, scanlines, vignette, side rails, agency name, op codename. Stored as a single `tweaks` JSONField on `SiteSettings` with a `default_tweaks()` helper that re-merges defaults on save so the on-disk JSON always has the full schema
- Migration `exodus/0016_sitesettings_tweaks` adds the `tweaks` field

## v0.14.34
- Fix: the **edit-conflict banner is now actually visible**. Previously the banner was rendered as a normal block element at the top of the agency sheet, which meant if you were scrolled down (e.g., looking at the projects section) and your save was rejected by another player's concurrent edit, the banner appeared above your viewport and you never saw it — you only saw the option silently disappear from the UI as the state refreshed. Now positioned `fixed` at the top-right of the viewport with a solid yellow background, drop shadow, slide-in animation, and a `⚠ EDIT CONFLICT` heading
- Section-specific messages: a conflict on `projects` says *"Another player just changed the projects list. The view has been refreshed — your last action was NOT applied. Click again if you still want it."*; conflicts on bases say *"Another player just edited &lt;section&gt; on this base..."*; text-input sections still ask for a re-blur
- Banner duration extended from 6s to 9s so longer section names (e.g., `base:7:facilities`) have time to read; multiple conflicts no longer prematurely dismiss each other (each banner tracks its own timestamp)
- `role="status"` + `aria-live="polite"` for accessibility

## v0.14.33
- Fix: extends the v0.14.32 multi-player concurrency fix to **projects**. Every write that touches `Agency.projects` (the section endpoint, dark grants, live testing, stimulants / unlock / synth, fringe-effect roll-modify branches, complete-project, project rolls) now goes through an atomic compare-and-swap on the shared `section_versions["projects"]` slot. Two players adjusting projects at the same time can no longer silently overwrite each other
- New `PATCH /api/agencies/<id>/section/projects/` endpoint with `If-Match` semantics, identical contract to the other 12 section endpoints from v0.14.32
- The ~12 per-project fetch sites in the React `_projects.html` module now route through a new `useProjectActionFetch` hook that automatically attaches the current `If-Match`, refreshes state on `409 Conflict`, and surfaces the same yellow conflict banner as the other section saves. `DarkGrantsModule` and `ProjectsModule` both opt in
- Backend `_with_projects_cas` helper centralises the CAS pattern for `projects` writes — force-write paths retry up to 5 times to mask spurious cross-project conflicts; `If-Match` paths fail fast with 409. Side effects (NPC creation, mental-load updates, BaseXpLog rows, AgencyStatLog rows) are intentionally hoisted *outside* the CAS loop so retries don't duplicate them
- Bonus correctness fix: experience / integrity decrements (live testing, overclocked equipment, child prodigy) now use atomic `F()` updates instead of read-modify-write — closes a pre-existing lost-update race on those fields
- Test suite grows to 37 tests (was 27); 5 new project-specific tests including a live-server race test that fires two concurrent project writes and asserts exactly one wins. 20/20 race executions clean across 5 sequential runs

## v0.14.32
- Fix: **multi-player concurrent edits to agency / base sections no longer silently overwrite each other.** When two players added different items to the same Bifrost base, the second player's write was being silently dropped (the old `existing.issubset(proposed)` guard rejected the proposal but didn't surface the rejection). Reported symptom: "when more than one player was updating the bases in Bifrost it didn't save correctly"
- New per-section `PATCH` endpoints under `/api/agencies/<id>/section/<key>/` (12 agency-level keys: header / alliance / notes / integrity / attributes / specializations / merits / flaws / assets / fleet / history / admin-flags) and `/api/agencies/<id>/bases/<base_id>/section/<key>/` (11 base-section keys), each with optimistic concurrency control via HTTP `If-Match` header. Stale writes return `409 Conflict` with the current version and value; the React frontend shows an inline yellow banner ("another user updated this section — refreshed") and re-hydrates the affected section. Implementation uses atomic compare-and-swap on the version column so it's correct on SQLite (where `select_for_update()` is a no-op)
- Migration `agencies/0035_add_section_versioning` adds `Agency.section_versions` (per-section version map) and `Base.version` (row-level counter). SQLite tuned for safe concurrent writes: WAL journal mode, `synchronous=NORMAL`, `transaction_mode="IMMEDIATE"`, 20-second busy timeout. Test database now file-based for reliable concurrent test coverage
- Player rule clarified: non-admin players on player-agency bases can ADD merits / facilities / equipment but cannot REMOVE them. Removal attempts now return an explicit `403 Forbidden` instead of the old silent drop
- Legacy `PUT /api/agencies/<id>/` and `PUT /api/agencies/<id>/bases/<base_id>/` endpoints still work as compatibility shims (now atomic and version-bumping) so MCP tools and any older code paths keep working. Frontend agency sheet adds `useSectionSave` and `useBaseSectionSave` hooks in `_utilities.html` plus a dispatcher in `_app.html` that automatically routes existing module saves to the right section endpoint with `If-Match`
- New regression test suite `agencies/tests/test_section_concurrency.py` — 27 tests across 6 classes including a live-server race test that fires two concurrent `PATCH`es at the same base section and asserts exactly one wins with `200` and one returns `409`. Permanent guard against the Bifrost bug

## v0.14.31
- Light/dark theme now applies to **all map types** — World Map (Leaflet), City Map (Leaflet), Star Map (Three.js), Battle Map and Battle Map Editor (canvas hex grids). Toggling the theme repaints the void background, grid lines, axis lines, and FTL route connection lines without a page reload
- Terrain visuals (planets, nebulae, asteroids, suns, debris, etc.) and token side colors (cyan players, red enemies) keep their semantic colors in both themes — they're like icons, not chrome
- Added a shared `--map-void` / `--map-grid-fill` / `--map-grid-stroke` / `--map-axis` / `--map-route-faint` / `--label-shadow` CSS palette in `foundation.css` and a `themechange` custom event dispatched by the toggle so canvas/Three.js scenes can re-render

## v0.14.30
- New **light/dark mode toggle** in the top nav (☀ / ☾). Theme preference is persisted in `localStorage` and applied before paint to avoid a flash of dark content on first load
- Added a `[data-theme="light"]` palette in `static/css/foundation.css` that flips backgrounds, text, and borders, and darkens `--accent-primary` / `--accent-warning` so the existing pattern of `color: var(--bg-dark)` on accent-colored buttons/badges/banners stays readable in light mode
- Replaced three hardcoded `rgba()` panel/nav backgrounds with new translucent CSS variables (`--bg-panel-translucent`, `--nav-bg`, `--nav-bg-mobile`) so glass panels and the sticky nav theme correctly

## v0.14.29
- Fix: **Fringe Science Lab** facility disappeared from the live BaseConfig (overwritten by a subsequent admin-UI save of the config JSON). Science characters with the Fringe Science Labs pulling string could not see or build the facility because the definition itself was missing from the config
- New migration `agencies/0034_reseed_fringe_lab_facility` re-adds the entry idempotently on container start
- Bundles the v0.14.28 fix (base `hidden_sections` incorrectly redacting player-agency bases; v0.14.28 tag was built but never reached production)

## v0.14.28
- Fix: base `hidden_sections` (a GM-only redaction tool for NPC bases) was incorrectly applied to player-agency owners too. Result: if a section was flagged on a player-agency base (e.g. via the cyber terminal hack-reveal flow, or a mis-click in the GM UI), the base's own members saw the section as CLASSIFIED and could not add facilities / merits / equipment there. `serialize_base` now bypasses `hidden_sections` when the base's agency is a player agency, matching how `is_field_visible` already handles field-level visibility
- Observed on Bifrost's Grimmorgap base, where rasmus (Bisgård) saw all facilities classified and couldn't build

## v0.14.27
- Site Settings → new **BASE ACCESS** tab with one toggle per character class (soldier, science, engineer, fixer, AI). Checking a box unlocks that class's class-locked base-building items (locations, merits, facilities, equipment) for every character
- Intended for campaigns that lack a character of a given class — GMs can open up the mechanics instead of leaving them inaccessible. Superusers are unaffected (always see everything); "general" items remain available to everyone
- Flags are stored on the `SiteSettings` singleton as a JSON map and honored by `serialize_base_config()` when it filters per-class visibility
- Migration `exodus/0015_sitesettings_class_unlock_flags`

## v0.14.26
- GM Workspace Timeline tool at `/gm/timeline/` — chronological events (Session / Plot Beat / World Event / Note) with in-game date auto-sort, type chips, type filter, markdown description, tags
- GM Workspace Campaign Log tool at `/gm/campaign-log/` — per-session recaps with session number, real-world played-at date, in-game date, markdown summary, tags. "+ NEW" auto-increments the session number
- Both tools share the same EDIT / SPLIT / PREVIEW mode toggle, auto-save, and list-plus-editor shell as Story Ideas
- Sidebar extracted to a reusable partial `_sidebar.html` so all three GM tools show identical navigation with an active-state highlight based on the current page

## v0.14.25
- GM Story Ideas editor: replaced the single PREVIEW button with a proper segmented EDIT | SPLIT | PREVIEW toggle. SPLIT shows the markdown textarea and the rendered preview side-by-side for long notes
- Selected view mode is remembered across notes and reloads via localStorage

## v0.14.24
- Wrap GM workspace + briefs React/JSX blocks in `{% verbatim %}` so Django's template parser leaves the JSX object literals alone (was producing a 500 TemplateSyntaxError on `/gm/story-ideas/`)

## v0.14.23
- New GM Workspace at `/gm/` — superuser-only React SPA with sidebar for future GM tools. First tool is "Story Ideas": titled, tagged, pinnable markdown notes with live preview, auto-save, and full CRUD
- GMs can selectively share specific notes with specific players via a multi-select toggle, or share with all players in one click
- New player-facing page at `/my-briefs/` — read-only list and detail view of notes shared with the logged-in player, rendered as markdown
- BRIEFS nav link appears for players only when they have at least one brief shared with them, with a count badge next to it
- GM nav link appears for superusers, next to SETTINGS / ADMIN
- New `gm_workspace` Django app with `StoryIdea` model, `/api/gm/story-ideas/` and `/api/my-briefs/` endpoints, superuser-gated backend with 404 (not 403) on player access to non-shared briefs to avoid leaking existence

## v0.14.22
- Agency HISTORY table's DECISION and CONSEQUENCE columns render as wrapping textareas instead of single-line inputs, so long narrative entries are readable and editable in place

## v0.14.21
- Fix character XP donation double-counting — donating XP to an agency was deducting the amount twice (once from `character.experience` on the backend, once from `remaining` on the frontend via the XpTransferLog sum). A 15 XP donation ended up costing 30 XP of surplus
- `character.experience` is now the stable "total earned" and is no longer decremented on donation; the XpTransferLog is the sole source of truth for donations (matching how the frontend has always displayed it)
- Frontend donate check now validates against actual surplus (`remaining`) instead of raw earned, with a clearer "you have N available to donate" message
- Retractions (admin-only negative transfers) still work correctly — the log sum decreases, freeing up surplus naturally

## v0.14.20
- Fix comms edit/delete CSRF 403: removed redundant `headers` from `api()` calls that overwrote the default CSRF token

## v0.14.19
- Superusers can now edit message content and thread titles inline in comms
- Pencil icon (&#9998;) appears next to the thread title and each message timestamp for staff users
- Clicking opens an inline editor with SAVE/ESC controls (Enter saves, Escape cancels)
- Superusers can also delete individual messages via the &#10005; icon next to each message
- Edited messages show an "(edited)" indicator next to the timestamp
- New `edited_at` field on Message model tracks when a message was last edited
- New API endpoint `PUT/DELETE /api/comms/threads/<id>/messages/<msg_id>/` for message editing/deletion
- Edits and deletions are broadcast to WebSocket clients in the thread

## v0.14.18
- News dispatch editor now shows player names in the EYES ONLY PLAYER dropdown. The templates were reading `u.username`, but `/api/comms/users/` returns `{id, displayName, portrait}` — so options rendered blank. Fixed in both the create form (`list.html`) and the edit form (`detail.html`) with a `displayName || username || User ${id}` fallback chain

## v0.14.17
- NPC dossier creation (`POST /api/npcs/`) now accepts any agency, not just non-player agencies. The prior `is_player_agency=False` filter silently dropped the agency link when admins tried to create a dossier for a Bifrost NPC, leaving an unlinked record
- Admin access is already required, and the superuser update path already allowed any agency, so the create path was inconsistent

## v0.14.16
- News dispatches now auto-derive `game_date_sort` from the free-text IN-GAME DATE field on create and update, so UI-entered dates like "May 5, 2036" or "9 February 2036, Evening" land in the correct chronological slot without needing a separate sort key
- Uses `dateutil.parser` with `fuzzy=True`, falls back to 2036-01-01 anchor when only partial info is given, ignores unparseable input
- Adds `python-dateutil>=2.8` to requirements.txt
- Explicit `gameDateSort` from API callers still wins over the derived value

## v0.14.15
- News API accepts ISO-8601 strings for `gameDateSort` (including trailing `Z`) and coerces them to real datetimes before assignment, so MCP/PUT callers can finally set the chronological sort key
- Bad/unparseable sort values now fall back to `None` instead of bricking the row with a stringified `DateTimeField`

## v0.14.14
- Battle map and map editor canvases support zoom in/out (40% – 250%)
- Floating zoom toolbar in the top-left of the canvas with −/+/⟲ reset buttons and a percentage label
- Ctrl/⌘ + mouse wheel zooms toward the cursor and keeps the hex under the pointer stable
- Plain scroll / scrollbars still pan the wrap natively, so oversized grids don't need a dedicated drag mode
- HEX_SIZE now derives from BASE_HEX_SIZE × VIEW_ZOOM via a live getter so all downstream math (hex/pixel conversions, drawHex, terrain visuals) picks up the zoom automatically

## v0.14.13
- New **Battery Banks** module section with five tiers (L1 Basic Battery Bank → L5 Fusion Battery Core)
- Adds battery capacity 3 / 6 / 10 / 15 / 25 with scaling slot, crew, energy, maintenance, and XP cost
- Drop any tier on a class to boost its combat battery_power pool so shields and heavy guns can sustain fire

## v0.14.12
- Ship modules grow weapon and defence profiles — damage, range, size bias, shields, battery
- ShipType gains base_shield and base_battery_power; drones 2 battery → titans 24
- ShipModule gains shield_delta, battery_delta, battery_cost, weapon_damage, weapon_range, weapon_min_range, weapon_size_bias, weapon_travel_turns
- Shields tier family now provides real temp-HP (L1 +3 → L5 +18) and raises battery capacity so you can actually run them
- Fighter Guns are short-range anti-small (size_bias -2 to -3), Main Guns medium-range anti-large (+2 to +4), Titan Cannons capital spinal (+5 to +8 bias, 3-8 battery cost per fire)
- Anti-Small-Craft Missiles enforce a minimum range — they can't fire closer than 2-3 hexes — with slow travel turns and strong anti-small bias (-3 to -5)
- Torpedoes are long-range anti-large (+3 to +5), slow travel (1-3 turns), higher damage the further up the tier
- Sensors already handled in v0.14.11 via scanning_delta
- compute_class_stats returns shield, battery_power, and a new arsenal list of installed weapons with their individual profiles (damage/range/min_range/size_bias/travel/cost)
- Class editor adds SHIELD and BATTERY pills next to HEALTH, plus a new ARSENAL block listing every installed weapon with its stat line
- Settings → Ship Types / Ship Modules expose every new field for tuning
- Battle detail panel grows SHIELD + BATTERY rows and a compact arsenal section per participant

## v0.14.11
- Ship combat stats round out with **scanning** (sensor rating) and **size** (surfaced from the existing StarshipClass.size field)
- ShipType gains base_scanning: drone 2 / solo 3 / shuttle 2 / cruiser 3 / support 4 / carrier 3 / dreadnaught 4 / titan 5
- ShipModule gains scanning_delta; seeded: standalone sensor_array +1, Sensor Suites L1→L5 +1/+2/+3/+5/+8
- compute_class_stats now returns scanning and size alongside the other combat stats
- Class editor, settings Ship Type / Ship Module editors, and battle detail panel all show SCAN and SIZE pills next to HEALTH/SPEED/DEFENSE/ARMOR/INIT

## v0.14.10
- Ship combat stats: health, speed, defense, armor added to ShipType baselines and ShipModule deltas
- Smaller hulls ship with more speed, defense, and initiative; bigger hulls ship with more health and armor. Seeded ladder: drone 3 HP / 6 speed / 5 def / 0 armor → titan 100 HP / 1 speed / 0 def / 8 armor
- Tiered Armour modules L1-5 add 1→6 armor (heavier tiers shave speed); tiered Shields L1-5 add 1→4 defense and 3→18 HP; tiered Manoeuvring Thrusters L1-5 add 1→3 speed + matching defense; tiered Sublight Engines L1-5 add 1→5 speed; heavy guns (main_gun L4/L5, titan cannon L3-5) apply a speed penalty
- compute_class_stats now returns health/speed/defense/armor/initiative_bonus alongside the existing totals
- Class editor (Starships page) shows a second stat row with colour-coded HEALTH / SPEED / DEFENSE / ARMOR / INIT pills
- Settings → Ship Types editor exposes the new baselines; Settings → Ship Modules editor exposes the new deltas
- Battle detail panel shows a 2-column combat stat grid per selected participant, live through compute_class_stats so module edits propagate without reload
- Simulator rewritten to use real stats: attack successes minus target.defense are raw hits, damage is max(0, hits − target.armor) applied to health. Results now report avg_player_survivors / enemy_survivors and avg hull % as fractions

## v0.14.9
- Fix: spacebattle pages threw "Uncaught SyntaxError: Invalid or unexpected token" because the _terrain_render.html partial opened with a multi-line Django {# … #} comment which Django's template engine only parses as single-line, so the comment body leaked into the script block
- Replaced with a plain JS /* … */ block comment so the content is inside the <script> section properly

## v0.14.8
- Spacebattle terrain now has procedural per-type visuals instead of flat colored hexes
- Asteroid fields render as scattered rocky chunks with shading; nebulas as overlapping coloured gradient blobs + speckle stars; debris fields as angled metal fragments; planets as shaded discs with crescent shadow and terminator line (5 palette variants); suns with radiating rays and a glowing core; gravity wells as concentric curvature arcs converging on a black dot; minefields as a grid of spiked mine markers; stations as hub + solar-panel arms; scenario zones as dashed hex outlines with a central Z; custom stays as the old colored fill + glyph
- Rendering is deterministic per (q, r) via a hashed mulberry32 seed so tokens don't shimmer between redraws
- New shared template partial spacebattle/_terrain_render.html exposes drawTerrainVisual() used by both the battle view and the map editor

## v0.14.7
- Space battle terrain, templates, and reusable battle maps
- New models: BattleTerrain (per-hex, unique per (battle, q, r)), TerrainTemplate (reusable relative-offset stamps), BattleMap (full saved space map with grid dims + terrain list)
- Ten terrain types seeded as choices: asteroid, nebula, debris, planet, sun, gravity well, minefield, station, zone, custom — each with a default color + unicode glyph that can be overridden per instance
- Terrain is **visual-only** — mechanics are GM-adjudicated; metadata JSONField reserved for a future rules engine
- Battle page TERRAIN button (superuser-only) toggles placement mode with a terrain type dropdown; click empty hex to place, click existing to delete
- APPLY MAP button pops a saved map picker and replaces the battle's grid + terrain in one call
- BATTLE MAPS nav link (superuser-only) opens a list of saved maps with full canvas editor at /spacebattle/maps/<id>/
- Map editor: click to paint terrain, rename/resize/clear/save, trims out-of-bounds terrain on resize
- Terrain changes broadcast as terrain_added / terrain_updated / terrain_removed websocket events so live viewers update without reload
- API: /terrain/ CRUD, /terrain-stamp/ applies a TerrainTemplate at a chosen origin (skips occupied hexes unless replace=true), /terrain-templates/ CRUD, /battle-maps/ CRUD, /battle-maps/<id>/apply/ copies grid + terrain onto a target battle

## v0.14.6
- Spacebattle rollback + fork (Release G of 7 — feature complete)
- POST /battles/<id>/rollback/ undoes the last N non-reverted log entries; damage entries restore the before-snapshot of maintenance_state/current_crew/status from the log payload; move entries reset q/r/facing; other action types are just marked reverted
- POST /battles/<id>/fork/ creates a read-only clone of a battle with the same participants for what-if scenarios
- UNDO and FORK buttons (staff-only) in the battle page controls
- The 7-release spacebattle feature ships complete across v0.14.0–0.14.6

## v0.14.5
- Spacebattle fire + damage adjudication (Release F of 7)
- Right panel now shows the selected participant's details (class, hull %, crew, side, agency)
- DECLARE FIRE button prompts for an optional weapon key then enters fire mode — next click on an enemy token logs a fire action
- APPLY DAMAGE button (staff only) prompts for hull delta / crew delta / note and writes directly to the canonical Starship record, broadcasting the update over websocket
- Every damage event captures before/after state in BattleLog for Release G rollback

## v0.14.4
- Spacebattle live moves + websocket sync (Release E of 7)
- Click a hex on the canvas to select the token in it; click an empty hex to move the selected token there
- Django Channels consumer at /ws/spacebattle/<id>/ fans out log + participant events to every connected viewer
- Moves, damage, log notes, and initiative rolls broadcast server-side and clients apply the update without a full reload
- Client auto-reconnects after 2s on drop

## v0.14.3
- Spacebattle participant placement (Release D of 7)
- PLACE button on the battle page opens a modal fleet picker
- Fleets grouped by agency in an optgroup dropdown; an "Unassigned hulls" bucket collects ships not in a fleet
- Side selector (PLAYERS / ENEMIES / NEUTRAL) applies to the next ship added
- Ships already in the battle are shown disabled with an IN BATTLE label
- Adding a ship POSTs to /api/spacebattle/battles/<id>/participants/ and reloads the board without closing the modal, so you can queue up a whole fleet in a few clicks
- Ships land at (0,0) for now — Release E adds drag-to-move

## v0.14.2
- Spacebattle list + canvas grid view (Release C of 7)
- /spacebattle/ battle list page with NEW BATTLE button (staff only)
- /spacebattle/<id>/ battle view with three-panel layout: info/initiative/participants, HTML5 Canvas hex grid, action log
- Pointy-top axial hex grid rendering, participant tokens drawn as coloured discs (cyan players, red enemies, grey neutral)
- START / NEXT TURN / END battle controls (staff)
- BATTLES nav link next to STARSHIPS (gated on show_starships site setting)

## v0.14.1
- spacebattle REST API + MCP tools (Release B of 7)
- Endpoints: /api/spacebattle/battles/, /battles/<id>/, /start/, /next-turn/, /end/, /log/, /simulate/
- Participant actions: /participants/, /participants/<id>/, /move/, /fire/, /apply-damage/
- Every mutating endpoint supports ?dry_run=true — projects state without persisting, so balance sims don't corrupt canonical ship records
- /simulate/ runs a pure-function toy combat model over the current battle state and returns aggregate stats (player_win_rate, avg_rounds, avg hull remaining). Safe for high-QPS balance work.
- Initiative uses d10 + ship_type.initiative_bonus, ties broken by smaller ship size
- Damage deltas write straight through to Starship.maintenance_state / current_crew / status, with every before/after state captured in BattleLog for Release G rollback
- Parallel commit to exodus-mcp adds list_battles / get_battle / create_battle / add_battle_participant / start_battle / battle_next_turn / move_participant / fire_weapon / apply_battle_damage / simulate_battle / get_battle_log MCP tools

## v0.14.0
- New **spacebattle** app — schema and migrations for the hex-grid tactical battle system (Release A of 7)
- Three models: Battle (top-level engagement), BattleParticipant (ship on the grid), BattleLog (append-only action log)
- Participants draw from the live Starship table via a PROTECT-guarded FK, so damage applied in battle flows back to canonical hulls
- Unique constraint prevents the same ship from being placed twice in one battle
- Configurable grid_width/grid_height per battle (default 20×15)
- ShipType gains initiative_bonus field; seeded per canonical type (drone +5 → titan −3)
- No UI yet — Release B adds REST + MCP, Release C adds the page

## v0.13.12
- Eight more tiered module sections seeded (L1–L5 each): Titan Cannon, Bridge, Anti-Small-Craft Missiles, Torpedo Launcher, Drone Bay (tiered), Solo Craft Bay, Manoeuvring Thrusters, Sublight Engines
- New **Titan** ship type (32-slot capital hull, size 9–12, 400 base crew); Titan Cannons restricted to titan + dreadnaught
- Drone Bay and Solo Craft Bay tiers restricted to carrier + titan
- Every tier of Sublight Engines sets provides_sublight, so a ship with any tier passes the "no sublight drive" warning
- Tier names follow the evocative naming pattern from v0.13.9 (e.g. Titan Cannon L1 Light Mass Driver → L5 Godbreaker Cannon)

## v0.13.11
- Settings → Ship Modules: grouped by section instead of a flat list
- Each tier family (Fighter Guns, Main Guns, Shields, Armour, Sensors) is a collapsible group header with its own heading and count; click the chevron to fold it away
- Standalone modules group by category with their own collapsible headers
- Sectioned rows show a prominent L1–L5 tier pill and drop the redundant category pill
- Dropped the per-row ▲▼ reorder arrows — tier order is now driven by level and standalone order by category, so the arrows were just noise

## v0.13.10
- Settings: Starships section split into four dedicated sidebar items — Starships (slot toggle + legacy import), Ship Types, Module Sections, Ship Modules
- Each subsection now has its own heading and description, making tuning catalogues less claustrophobic

## v0.13.9
- Ship module sections: tiered families of modules with 5 fixed levels
- New ShipModuleSection model + section FK/level field on ShipModule
- Seeded 5 sections with 5 tiered modules each: Fighter Guns (Single Auto Cannon → Twin Auto Cannons → Gatling Gun → Twin Gatling Guns → Vengeance Cannon), Main Guns, Shields, Armour Plating, Sensor Suites
- One module per section per class — installing any tier atomically replaces the existing tier in that section (single-click upgrade/downgrade)
- Class editor shows section name + level pill on installed modules and adds ◀ ▶ tier swap buttons per section row
- Add-module dropdown groups sections (tier families) at the top with optgroups, then standalone modules by category
- Settings → Starships gains a SHIP MODULE SECTIONS catalogue editor (reorder/add/edit/delete)
- Ship Module editor exposes a section dropdown + level input for manual catalogue authoring
- API: GET/POST /api/starships/module-sections/, PUT/DELETE /api/starships/module-sections/<id>/
- Module serializer + class module serializer both expose section_id/section_name/level

## v0.13.8
- Settings → Map Visibility now has a STARSHIPS toggle controlling whether players can see the starships page
- Staff always see the STARSHIPS nav link; players only when the toggle is on
- /starships/ view returns 403 for non-staff when the toggle is off (defence in depth)
- SiteSettings.show_starships (default False) + migration 0014

## v0.13.7
- GMs can now create starship classes, fleets, and ship instances for any agency (not just their own)
- NEW class prompt asks "which agency owns this class?" with a numbered picker (0 = SHARED)
- NEW fleet prompt asks for target agency
- BUILD HULL from a shared class asks which agency receives the hull; agency-owned classes inherit their class's agency
- Class sidebar groups by owning agency name (with SHARED bucket pinned at bottom) so GMs can scan multi-agency catalogues
- Backend: api_classes POST accepts created_by_agency_id for superusers; api_fleets and api_ships already supported agency_id override

## v0.13.6
- Legacy Agency.fleet TableModule removed from the agency sheet (Release G of 7 — final)
- Replaced with a small info card linking to the Starships page
- The Agency.fleet JSONField and API serialization are untouched for now; a future v0.14.x can drop them once the real records are verified as authoritative
- Completes the starships feature — schema, catalogues, class editor, ship build flow, fleets, legacy import, and cleanup all shipped on the 0.13.x track

## v0.13.5
- Legacy fleet import shipped (Release F of 7)
- `python manage.py import_legacy_fleets` management command with --dry-run, --force, --agency flags
- Settings → Starships now has a LEGACY FLEET IMPORT panel with status label, PREVIEW (dry run), IMPORT, and FORCE RE-IMPORT buttons
- Button label shows "(N)" count of pending entries; disables when nothing is pending
- API endpoints: GET /api/starships/legacy-status/, POST /api/starships/import-legacy/ (both superuser-only)
- Imported hulls are tagged with "[legacy-import]" in notes so re-runs are idempotent by default
- Fuzzy ship type matching on the legacy shipClass string: exact key/name match first, then substring rules (drone/solo/cruiser/carrier/dreadnaught etc.), with cruiser as the default fallback
- Imports create per-agency StarshipClass entries named after the legacy string, so GMs can tune each immediately after import
- Agency.fleet JSON blob is left untouched — Release G will hide it from the UI

## v0.13.4
- Fleet grouping shipped (Release E of 7)
- FLEETS tab on /starships/ with per-agency list, NEW button, fleet editor
- Fleet editor: name, commander, notes, ship count, assigned ships list with REMOVE buttons, add-ship dropdown of unassigned hulls in the same agency
- Ship editor gains a FLEET dropdown so hulls can be reassigned directly from the ship detail view
- Deleting a fleet unassigns its ships (sets fleet_id null) rather than cascade-deleting them
- api_fleets list/create/detail CRUD; PUT /api/starships/ships/<id>/ now accepts fleet_id (validates same-agency)

## v0.13.3
- Starship instance build flow and SHIPS tab shipped (Release D of 7)
- BUILD HULL button on each class creates an under_construction hull
- SHIPS tab sidebar groups hulls by status (Under Construction, Active, Damaged, In Dock, Decommissioned, Lost) with status-coloured dot
- Ship editor: name, hull number, status transitions, current crew vs class-required, maintenance %, location (StarSystem picker), commissioned date, notes
- Construction progress bar for under_construction ships with RECORD BUILD ROLL input — auto-promotes to Active and stamps commissioned_at when successes hit the class threshold
- api_ships list/create/detail/delete; api_ship_construction_roll endpoint handles progress rolls server-side
- Visibility: superuser sees every hull; players see only their own agency's
- Star systems list lazy-loaded into the location dropdown on first ship selection

## v0.13.2
- Starship class editor shipped as a standalone /starships/ page (Release C of 7)
- New STARSHIPS link in the main nav, visible to all authenticated users
- Class list sidebar grouped into "MY AGENCY" and "SHARED" (GM-owned classes visible to everyone)
- NEW button creates a class; GM superusers can optionally flag it as shared
- Class editor panel: name, ship type picker, size stepper, description, base build XP, required successes, lock toggle (GM), delete button
- Live derived stats: slot usage bar (green → amber → red), required crew, energy, maintenance, build XP total, SUB/FTL status pills
- Warnings panel color-coded by severity: over slot budget, missing sublight/FTL/power, out-of-range size, modules restricted to other ship types, modules too big for the hull
- Installed modules list with slot/crew breakdown, quantity stepper, and remove button
- Add-module dropdown grouped by category, with slot cost in each option label
- Soft vs hard slot-budget enforcement honours the Settings → Starships toggle — 422 response on hard-fail returns the class with `_enforced_errors`
- Ships and Fleets tabs rendered but disabled as placeholders for Releases D and E
- Avoided touching the Babel-standalone agency sheet entirely; classes live on their own page to sidestep transpilation risk

## v0.13.1
- Settings → Starships tab: Ship Types and Ship Modules catalogue editors (Release B of 7)
- Both catalogues reuse the reorder / expand-edit pattern from ResourceType
- Ship Types expose slot budget, size bounds, baseline crew/energy/maintenance
- Ship Modules expose slot cost, crew/energy/maintenance deltas, sublight/FTL flags, min hull size, build-cost XP delta, research XP, category, and restricted-to-types (comma-separated key list)
- Category filter dropdown on the module list, add-module form includes a category picker
- SiteSettings "enforce slot budget" toggle exposed here (used by Release C's class editor)
- SUB/FTL pill badges in the module summary rows

## v0.13.0
- New **starships** app — schema, migrations, and seed data for the upcoming starship module system (Release A of 7)
- Six new models: ShipType, ShipModule, StarshipClass, ClassModule, Starship, Fleet
- Real ShipModule table (not a JSON catalogue) so modules can be queried and reordered without DB blob rewrites
- Seeded 7 ship types (drone / solo / shuttle / cruiser / support / carrier / dreadnaught) and 18 starter modules across propulsion, power, weapons, defense, sensors, quarters, cargo, command, and hangar categories
- Hangar modules (drone bay, fighter bay) restricted to carrier/support via restricted_to_types JSON list
- StarshipClass carries build_cost_xp + build_required_successes (FTL-project-style construction rolls)
- Starship carries current_successes for under-construction state and auto-promotion, plus location FK → StarSystem for the star map overlay in Release D
- SiteSettings gains enforce_ship_slot_budget toggle — when false, class editor warns on overshoots; when true, rejects them
- No UI yet — Release B will add the catalogue editors in Settings > Starships

## v0.12.58
- Star map planet rows now show a color-coded life badge (PREBIO / BACT / CELL / PLANT / ANIMAL / INTEL) next to the planet type
- "None" and "unknown" lifeType render muted so only real life stands out

## v0.12.57
- Fix: star map planet list and count were hidden for GMs on unscanned stars — now GMs see ground truth unconditionally (detected via scanLevelTruth flag from the serializer)

## v0.12.56
- Star map info panel now lists planets of interest (name, type, water/habitable badges) when a star has been scanned
- Planet list is fetched lazily and cached per star id so the hover loop stays quiet
- Filtering respects existing rules: superusers see all, players see only discovered + visible planets

## v0.12.55
- Star map: resource bars now render in the order defined in Settings > Star Map
- Resource names, colors, and icons on the map come from the ResourceType catalogue, so GM edits in settings flow through to the map without code changes
- Hardcoded fallback kept for unauthenticated demo views

## v0.12.54
- Settings: up/down arrow buttons on each resource type row to reorder the list
- Reorder rewrites every row's order field with its new index, so ties (e.g. freshly added types with order=0) move correctly
- First/last row arrows are disabled to avoid out-of-bounds moves

## v0.12.53
- Fix: resource types list endpoint was broken since v0.12.51 because @login_required was accidentally decorating a helper instead of the view — settings page now loads resource types again

## v0.12.52
- Settings: per-star ground-truth resources are now editable from the Star Map page
- Pick a star from the planet dropdown to see every configured resource with its current value, unit, and typical range
- Numeric inputs + SAVE button write straight to the star's resources; missing values render as 0
- Fixed resource display which was broken after the unit refactor (was rendering "[object Object]%")
- Write path accepts either {key: int} or {key: {value}} and always stores compact integers

## v0.12.51
- Settings: resource types now expose full tuning in-app — unit label & meaning, typical min/max, rarity weight, scan brackets (wide/narrow), sort order
- Expandable edit panel per resource type with SAVE button; freshly added types auto-open for tuning
- Summary row shows "min–max unit ×rarity" at a glance
- GMs no longer need Django admin to dial galaxy-wide resource abundance

## v0.12.50
- Fix: agencies migration 0032 crashed on fresh DBs with "duplicate column name: agency_id" because 0031 already creates the FK in its final form — made 0032 a no-op, dependency chain preserved

## v0.12.49
- Rebuild-only release (no code changes)

## v0.12.48
- Star map resources: absolute unit quantities instead of 0–100 percentages
- ResourceType gains unit_label, typical_min/max, rarity_weight, scan brackets
- Seeded six canonical resources: ice (carrier loads), metals (kt ore), rare earths, helium-3 (canisters), hydrocarbons (tanks), exotic matter (fragments)
- Scan levels return {min, max, unit} brackets — level 3 is exact
- Procedural seeder uses per-resource ranges modulated by scarcity factor
- Star info panel shows "20–60 carrier loads" instead of "42%"
- First release after git/production sync — prior v0.11.x and v0.12.0–0.12.47 entries not in this changelog

## v0.10.6
- Fix: agency page Babel crash — removed template literals and IIFEs from JSX

## v0.10.16
- Agency sheet refactored from 3237 lines into 6 component files + 28-line shell
- Components: _utilities (182), _core_modules (839), _table_ftl (548), _changes (253), _bases (834), _app (617)

## v0.10.25
- Stimulant cocktails for fringe projects: Modified Cocaine (+2), LSD (+3), Shrooms (+2), Exotic Animal Venom (+4)
- Stacking penalty: +10% risk per additional substance
- Only science class and GM see results; project owner sees "Stimulant Cocktail Active"
- Project locked until GM unlocks after completion roll
- Side effects: mental load, bashing damage, completion loss (applied to project owner)

## v0.10.23
- Live Testing on fringe projects: Small Animals (+1, 5% ML), Large Animals (+2, 9% ML), Human (+5, 23% ML + 17% integrity), Off the Books (+5, 23% ML, requires merit)
- Project player field as character dropdown with data migration
- Projects redesigned as card layout with progress bars
- Dark Grants risk halved twice (now d100 at 9/14/23%)
- Agency sheet refactored into 6 component files

## v0.10.5
- Fix: agency page crash when projects is CLASSIFIED or null

## v0.10.4
- Dark Grants: science class activates on fringe projects at level 1-3
- Permanently adds +level dice to completion rolls
- Risk: 1d10 per level, each 1-3 links a random NPC agency to the project
- Linked agencies shown in red, one-time activation per project
- Requires Dark Grants pulling string

## v0.10.3
- Fringe slot limit: max active fringe projects = Science score
- Slot counter shown above projects table for science class
- Fringe button disabled when no slots available
- Discarded projects free fringe slots and are hidden from non-admin
- Completed projects also free fringe slots

## v0.10.2
- Fringe is permanent — once marked, cannot be undone. Confirmation dialog before marking.

## v0.10.1
- Fringe projects shown with 🖐 hand glyph icon (Fringe TV show inspired)
- Science class can toggle fringe status by clicking the glyph
- Faded when not fringe, bright when marked

## v0.10.0 — Science Expansion
- Science class can mark projects as "Fringe"
- Fringe column only visible to science class and GM
- Non-science players don't see the fringe flag in the API or UI

## v0.9.86
- Helper NPC goes "Compromised — Underground" when concealment fills
- Detected by agency name recorded on the NPC
- Banner on dossier page shows compromised status and detecting agency
- GM decides when the operative resurfaces

## v0.9.85
- Terminal rules updated: intercepted channels section, terminate vs close connection distinction, lock icon mention

## v0.9.84
- Cyber terminal usable on intercepted channels at -4 penalty to all rolls
- Orange banner in terminal warns "INTERCEPTED CHANNEL — All rolls at -4 difficulty"

## v0.9.83
- Intercepted threads list auto-refreshes every 15 seconds

## v0.9.82
- Fix: terminate removes intercepted threads from ALL past attackers, not just active sessions

## v0.9.81
- Terminating a chat removes all intercepted threads (hidden memberships) from attackers on that thread

## v0.9.80
- Lock icon on terminated chats in channel list

## v0.9.79
- Terminal polls status every 10s — reacts to terminate by other party
- System alert posted when chat is terminated so both parties see it via WebSocket

## v0.9.78
- Rename CLOSE to TERMINATE (chat) / TERMINATE CHAT (terminal)
- Fix: terminate stays in chat view instead of jumping out

## v0.9.77
- Fix: intrusion detection now per-session — multiple attackers can each be detected independently
- Fix: tuple unpack crash on Gain Access (Distributed Consciousness check)
- Fix: helper concealment detection runs on every deploy, not just when already detected
- Fix: WebSocket auto-reconnects on disconnect — chat messages update in real-time again
- Removed dead code in _resolve_deploy for close_connection

## v0.9.76
- Mental load penalizes all cyber terminal actions and sweep rolls
- Shown in pool description and active modifiers panel

## v0.9.75
- Force Bad Deals and Gain Base Access now create agency conditions with difficulty
- All deploy actions that affect an agency create trackable conditions with Sweep & Clear

## v0.9.74
- Fix: NPC agency sweep info now correctly finds best dossier (was unreachable code)

## v0.9.73
- Fix: sweep info shows for GM viewing player agency — finds best player character
- Sweep explainer always visible when conditions exist

## v0.9.72
- Sweep & Clear explainer: shows dice pool breakdown (Intelligence + Computer + merits) and active merits
- NPC agencies: GM rolls using best dossier (highest Intelligence + Computer + merit modifier)

## v0.9.71
- Sweep pool moved to agency level — shared across all conditions
- Anyone with Computer skill can sweep, each roll costs 1 from agency pool
- GM sets agency sweep pool, visible to all members

## v0.9.70
- Fix: deploy actions now correctly resolve defender's player agency (conditions show on Bifrost)
- Fix: passive detection skipped when intrusion already detected — no redundant rolls
- All deploy handlers use shared _resolve_defender_agency helper

## v0.9.69
- Intrusion detected status is now permanent on the thread — red banner stays in terminal forever
- Thread.intrusion_detected flag set whenever detection succeeds

## v0.9.68
- Fix: deploy crash — target_project_index not passed to _handle_deploy

## v0.9.67
- Fix: defender agency/bases resolved for player characters (not just NPC aliases), falls back to player agency

## v0.9.66
- Removed old free-text CONDITIONS table from agency page, replaced by structured Cyber Conditions

## v0.9.65
- Cyber Conditions UI on agency page: shows active conditions with progress bar, Sweep & Clear button, GM pool allocation and remove controls

## v0.9.64
- Agency Conditions system: ransomware and shutdown deploys create structured conditions on target agency
- Each condition has difficulty (attacker successes) and Sweep & Clear mechanism
- GM allocates sweep pool, players roll Intelligence + Computer to clear
- Conditions displayed on agency page with progress tracking
- API endpoints for sweep rolls and GM condition management

## v0.9.63
- Remove Exfiltrate Communications deploy action
- Remove Backdoor Access pulling string from cyber terminal
- Merit rules in terminal only show merits the actor's class has access to
- Pulling string rules section shows only what the actor has

## v0.9.61
- AI merits in cyber terminal: Firewall (+rating defend/detect), Rapid Processing (+2 all), Network Puppet (+2 deploy), Overclock (+3 one attack), Distributed Consciousness (x2 deploy actions)
- Defend messages only shown to executor, attacker detects via Detect roll
- Action log entries no longer truncated, full multiline display
- Fixers can select Darknet Identity Broker pulling string

## v0.9.57
- Defend rules: one-use per thread, escalating chat alerts, +N to all detection rolls

## v0.9.56
- Defend reworked: one-time activation adds +success to detection rolls, chat alerts at each level, button greys out after use

## v0.9.55
- Core stats (Integrity, EXP, Zero-Day Pool) displayed on one line on agency page

## v0.9.54
- Engineers can only select Bot Farm pulling string (not all AI pulling strings)

## v0.9.53
- Engineers can select Bot Farm pulling string on NPC and character sheets

## v0.9.52
- Complete rewrite of terminal rules panel with all systems documented

## v0.9.51
- Digital Ghost merit adds +2 concealment levels for helpers

## v0.9.50
- Digital Ghost merit available to engineer class (was AI only), comma-separated class restrictions

## v0.9.49
- Digital concealment track displayed on NPC sheets with Computer 4+

## v0.9.48
- Helper list includes personal contacts with Computer 4+ (not just agency dossiers)

## v0.9.47
- Dossier helper system: agency NPCs and contacts with Computer 4+ can assist in terminal
- Helper bonus: (Computer + Wits) / 2 dice added to attack rolls
- Digital concealment track with escalating defender bonus on last 4 levels

## v0.9.46
- Sabotage project reduces completion points by number of successes (min 0)

## v0.9.45
- Sabotage project shows picker of declassified projects from defender's agency

## v0.9.44
- Projects can be classified/declassified, all existing projects marked classified
- New projects default to classified, checkbox column on agency page

## v0.9.43
- Deploy targets auto-resolve to defender's agency, base picker shows only defender's bases

## v0.9.42
- Zero-day checkbox renders immediately on action select (pre-computed variables)

## v0.9.41
- Fix blank comms page from JSX parsing issue in zero-day block

## v0.9.40
- Zero-day checkbox shows remaining count, greyed out when pool reaches 0

## v0.9.39
- Zero-day checkbox only shows when actor has Government Zero-Day Repository pulling string

## v0.9.38
- Show NPC persona modifiers for GM in cyber terminal

## v0.9.37
- Active modifiers panel in cyber terminal shows merit bonuses, pulling string effects, specialisations

## v0.9.36
- Zero-Day Pool displayed and editable on agency page (superuser only)

## v0.9.35
- Use Zero-Day Exploit checkbox on attack actions, pulling strings listed in rules panel

## v0.9.34
- Pulling strings affect cyber terminal: Bot Farm, Backdoor Access, Compromise Firmware, Digital Payload, Zero-Day Repository
- Agency zero_day_pool field added

## v0.9.33
- Cyber merits affect dice pools: Computer Aptitude, Digital Infiltration, Digital Ghost

## v0.9.32
- Close Connection requires no roll, no passive detection, silently removes traces

## v0.9.31
- Replace Corrupt Data with Shut Down Infrastructure (power, water, logistics, transport, media, comms)

## v0.9.30
- Gain Base Access reveals hidden sections on target base

## v0.9.29
- Discover Base unhides a random hidden base from defender's agency

## v0.9.28
- Ransomware can target a specific base via base picker

## v0.9.27
- Ransomware auto-targets defender's agency

## v0.9.26
- Deploy locked for everyone when no active session or deploys exhausted

## v0.9.25
- Deploy button locked when deploys remaining hits 0

## v0.9.24
- Hide success count for detect in action log

## v0.9.23
- Fix detect showing no feedback, defensive rendering for missing roll data

## v0.9.22
- Fix detect finding own sessions/backdoors in NPC-vs-NPC threads

## v0.9.21
- Fix detect with 0 successes falsely detecting dormant backdoors, hide dice for detect

## v0.9.20
- Hover tooltip on CLOSE buttons explaining permanent effect

## v0.9.19
- Close connection button in chat header, CONNECTION CLOSED banner, backend blocks messages

## v0.9.18
- Updated terminal rules with full session flow

## v0.9.17
- Intrusion detection posts a system alert message in the chat (red centered warning)
- Alert visible to all non-hidden thread members via WebSocket
- System messages styled distinctly from user messages

## v0.9.16
- Show passive detection result on every deploy action to increase tension

## v0.9.15
- Complete cyber session flow: Gain Access creates session with deploy limits (successes/2)
- Passive detection on Gain Access (1-4 successes) and each Deploy action
- 5+ successes = exceptional, no passive detection triggered
- Difficulty escalation: +1 per prior closed connection
- Active Detect: Resolve + Computer + 2 vs attacker successes, cached between actions
- Detect only shows INTRUSION DETECTED / NO INTRUSION DETECTED (no dice shown)
- Close Connection: locks thread, ends all sessions, blocks further actions
- Session state displayed in terminal (deploys remaining, detected status)
- Backdoor = unlimited deploys until connection closed

## v0.9.14
- CyberSession model for tracking active hacking sessions (deploys remaining, detection state, difficulty escalation)
- Thread connection closed state (prep for revised cyber flow)

## v0.9.13
- Steal Intel now requires target agency, picks a random classified field, unlocks it, and logs what was uncovered

## v0.9.12
- Deploy submenu with 11 operations: backdoor, ransomware, force bad deals, steal intel, discover base, base access, plant false intel, exfiltrate comms, sabotage project, corrupt data, close connection
- Each operation has its own dice pool (Wits/Intelligence/Manipulation + Computer/Investigation)
- Target pickers for agency and base where relevant

## v0.9.11
- GM can create NPC-to-NPC threads: pick persona + NPC target to test cyber terminal and roleplay NPC conversations

## v0.9.10
- Deploy action in cyber terminal locked until a successful Gain Access has been performed (GM bypasses)

## v0.9.8
- Fix: unskilled mental skills now apply -3 penalty (not -1); physical and social remain -1

## v0.9.7
- Dice roller applies -1 unskilled penalty when rolling a skill at 0 dots

## v0.9.6
- Dice roller on NPC dossier pages (superuser only) — pick attribute + skill, roll with NPC's stats

## v0.9.5 (2)
- Cyber terminal RULES button shows operations manual explaining each action, dice mechanics, and modifiers

## v0.9.4
- Hide cyber terminal button when posting as GM persona

## v0.9.3
- GM persona in comms now shows the user's avatar as portrait

## v0.9.2
- Fix: accounts migration not running (missing __init__.py in migrations package)

## v0.9.1
- User avatar upload on profile page (used as fallback portrait in comms when no character portrait exists)

## v0.9.0
- **Cyber Terminal**: hacking overlay for characters with Computer 4+ (green-on-black terminal UI)
- Actions: Gain Access (hidden thread surveillance), Deploy (backdoor), Defend (encrypt/sweep), Detect (reveal threats)
- WoD 2.0 dice roller: d10, success on 8+, 10s explode, exceptional success (5+), dramatic failure
- Dice pools: Intelligence/Wits/Resolve + Computer, specialisation bonuses, GM modifiers
- Intercepted channels section in sidebar shows threads gained via Gain Access (read-only)
- Hidden membership: hackers don't appear in roster/thumbnails of intercepted threads
- GM can set modifier dice and manually manage thread effects
- Comms improvements: member portrait thumbnails, clickable lightbox, GM persona system, per-thread persona memory, thread deletion, auto-refresh channels

## v0.8.57
- Channels list auto-refreshes every 15 seconds to pick up new threads, deletions, and alias changes

## v0.8.56
- GM persona now reflected in thread roster and thumbnails (shows GM/NPC identity instead of real user)
- Persona persists on the server per-thread so all players see the correct identity

## v0.8.55
- GM can choose persona (GM/SELF/NPC) when creating a new thread; choice carries into the thread

## v0.8.54
- GM (superuser) can delete threads via X button in thread header with confirmation

## v0.8.53
- Portrait thumbnails in comms thread header are clickable to open full-size lightbox

## v0.8.52
- Comms remembers chosen persona per thread until actively changed

## v0.8.51
- Superuser defaults to posting as GM persona in comms instead of self
- GM badge shown on GM messages; NPC dossier posting still available via dropdown

## v0.8.50
- Comms thread header now shows member portrait thumbnails instead of operative count text

## v0.8.49
- Hide dossier filter buttons when no visible NPCs match that filter for the current user

## v0.8.48
- Added new base facility type: Engineering Build Project Site (levels 1-5, XP cost matches project scale)
- Added new base facility type: Science Research Project Site (levels 1-5, XP cost matches project scale)

## v0.8.47
- Base notes now render as markdown with edit/view toggle

## v0.8.46
- Fix: naval equipment now requires Shipyard or Coastal Access merit — no more ships in mountain bases
- Equipment requirements now support location merit checks (type: "merit" in requiresAnyOf)

## v0.8.45
- Agency notes now render as markdown with edit/view toggle (same as operative dossier)

## v0.8.44
- XP transfer endpoint now supports negative amounts (retractions) for admins — properly logs and reverses transfers

## v0.8.43
- AI class restrictions — physical attributes and skills locked to 0 unless the Android merit (3-5 dots) is acquired
- Android merit added (AI class only) — enables synthetic body with human-likeness scaling by dot rating
- AI entity banner on stats panel showing locked/unlocked status
- Physical column greyed out with "(REQUIRES ANDROID)" label when locked
- Works on both operative character sheets and NPC dossiers

## v0.8.42
- Dossier pulling strings and merits now show descriptions in both admin and read-only views

## v0.8.41
- Fix: dossier list page crash — npcs variable not passed as prop to FilterBar component

## v0.8.40
- Fix: dossier page crash — moved React useState hooks out of IIFEs to component level

## v0.8.39
- Players can see stats (attributes, skills, health, merits, pulling strings, XP) on dossiers assigned to them (read-only)
- Stats hidden from players on dossiers not assigned to them
- All edit controls disabled in read-only mode

## v0.8.38
- NPC dossiers now auto-calculate XP costs for attributes, skills, specialisations, and merits above WoD 2.0 creation baseline (same as operatives)
- Creation incomplete warning on dossiers
- Hover tooltip on AUTO XP showing breakdown
- Dynamic mental load boxes on dossiers — 4 + floor((Composure + Resolve) / 2), with penalty zone and explainer

## v0.8.37
- XP tracking on NPC dossiers — total, manual, auto (pulling strings cost), and remaining
- Experience visible to all players, editable by admins

## v0.8.36
- Catalog-based merits and pulling strings on NPC dossiers — same picker system as operative character sheets
- Admins can add/remove merits and pulling strings on dossiers, filtered by NPC's class
- Non-admin players see merits and pulling strings as read-only

## v0.8.35
- Dossier list can now be filtered by agency — dynamic filter buttons appear for each agency that has NPC dossiers

## v0.8.34
- Personal NPC pulling string hidden from picker when player has no unlinked dossiers left

## v0.8.33
- Fix: NPC dossier linking on Personal NPC pulling strings — dropdown now correctly shows available NPCs, excludes only NPCs linked to OTHER entries (not the current one)

## v0.8.32
- Fix: pulling string/merit add now clears pending save timer to prevent race condition with debounced auto-save
- Increased reload delay after add/remove actions for more reliable server response

## v0.8.31
- Merits and Pulling Strings pages now accessible to all players (read-only)
- Players only see merits/pulling strings available to their class (general + class-specific)
- Add/Edit/Delete controls hidden for non-staff
- Nav links moved outside staff-only block

## v0.8.30
- Equipment requirements now support OR conditions (`requiresAnyOf`) — e.g. planes require Airstrip OR Carrier Strike Group
- All aviation units require Airstrip (Aviation L1+) or Carrier Strike Group
- All motorized units require appropriate Garage level
- Orbital Vehicles still require Space Launch Pad (Aviation L3+)

## v0.8.29
- Equipment requirements enforcement — equipment options are locked with a padlock icon if the base lacks required facilities
- Requirements checked programmatically via `requiresFacilities` field (facility key + minimum level)
- Locked equipment shown greyed out with tooltip explaining what's needed; hidden entirely for non-admins
- Equipment categories hidden for non-admins if no items are available or selected
- Naval Units and Motorized Units category visibility toggles added

## v0.8.28
- Operative contributions log on agency page — shows which player transferred how much XP, with character name, player name, amount, and date
- Scrollable list under CORE STATS, grouped with alternating row backgrounds

## v0.8.27
- Base creation API now accepts all fields (location type, merits, facilities, workspaces, equipment, coordinates) on POST
- MCP tools: create_base, update_base, delete_base

## v0.8.26
- Classified notes section on character sheet — private markdown notes visible only to the player and GM
- Red-bordered panel with "Visible only to you and the GM" disclaimer
- Hidden from other players on read-only view (API returns null for non-owners)

## v0.8.25
- Fix: Personal NPC pulling string picker now excludes dossiers already linked to another pulling string on the same character
- Fix: character portrait click behaviour — clicking empty portrait triggers upload for owners

## v0.8.24
- Flaws section on character sheet — players can add, edit, and remove flaws with name, rating, and description
- Flaws visible on read-only character view when present

## v0.8.23
- Replaced drag-and-drop with up/down arrow buttons for reordering facility categories and facilities

## v0.8.22
- Facility categories — facilities can be grouped into named categories with drag-and-drop ordering
- Drag-and-drop reordering for both categories and facilities within categories on base config page
- Add new categories with text input
- Each facility has an editable category field
- Agency base sheet displays facilities grouped by category in configured sort order

## v0.8.21
- Image upload in comms — attach images to messages via camera button next to input
- Images displayed inline in chat bubbles with click-to-enlarge lightbox
- Image preview shown before sending with ability to cancel
- Messages can now be image-only, text-only, or both

## v0.8.20
- Click-to-enlarge lightbox on character portrait images (edit and read-only views)
- Owners: click image to enlarge, click CHANGE bar to upload; non-owners: click to enlarge

## v0.8.19
- Explainer text above mental load boxes showing formula breakdown and penalty escalation

## v0.8.18
- Dynamic mental load boxes — total = 4 + floor((Composure + Resolve) / 2), last 4 boxes give penalties
- Penalty zone visually distinguished with red borders, safe zone with subtle borders
- Shows current/max and formula next to MENTAL LOAD label

## v0.8.17
- Fix: XP cost calculation now most efficient for the player — free creation dots cover the most expensive levels, XP only pays for the cheapest excess

## v0.8.16
- Specialisations section now shows rule hint: "+1 die when a skill roll matches a specialisation"

## v0.8.15
- XP protester much bigger (240x210px), slower walk (20s cycle), taller zone (210px)

## v0.8.14
- Bigger XP protester (160x150px) with wider sign that fits all message text

## v0.8.13
- XP transfer log — shows history of transfers with amount, agency, agency XP received, and date

## v0.8.12
- XP protester now twice as tall (120px), walks slowly (12s cycle), and gets its own dedicated zone above the EXPERIENCE header

## v0.8.11
- XP protester now bigger and walks across the full EXPERIENCE header line instead of the small remaining box

## v0.8.10
- Animated stick figure protester appears when XP goes negative — marches back and forth holding a random protest sign
- 10 random sign variants: "NEED MORE XP!", "XP OR RIOT!", "WILL WORK FOR XP", etc.
- Works on both character sheets and agency sheets

## v0.8.9
- Pulling strings management page at /pulling-strings/ — staff can add, edit, and delete pulling strings with inline editing and category filtering
- PULL STRINGS link added to navigation bar for staff

## v0.8.8
- Class restriction on merits — merits can be restricted to specific operative classes (Fixer, Soldier, etc.)
- Merit management page at /merits/ — staff can add, edit, and delete merits with inline editing, category filtering
- MERITS link added to navigation bar for staff
- Class-specific merits: Gun Fu (Soldier), Mechanical Aptitude (Engineer), I Know Someone (Fixer)
- 67 merits seeded in catalog (Physical, Mental, Social, Supernatural)

## v0.8.7
- Merit catalog system — game-level definitions with name, description, dot cost (fixed or variable), category, prerequisites, and mechanical effects
- Merits selectable from catalog on character sheet with dot rating picker
- Merit effects engine — merits can modify health, size, speed, willpower, and provide stat/skill bonuses and difficulty modifiers
- Derived traits (health, willpower, speed) automatically updated by merit effects
- MCP tools: list_merits, create_merit, update_merit, delete_merit
- API endpoints: GET/POST /api/merits/, GET/PUT/DELETE /api/merits/<id>/
- Django admin registration for MeritDefinition model

## v0.8.6
- Personal NPC pulling string picker now only shows NPCs assigned to the current player

## v0.8.5
- Hover tooltip on AUTO XP showing full calculation breakdown (attributes, skills, specialisations, merits, pulling strings)

## v0.8.4
- Personal NPC pulling string can now be linked to an NPC dossier (3 XP cost)
- Linkable pulling strings support — can be taken multiple times, each linked to a different NPC
- NPC dossier picker on linkable pulling strings in the character sheet
- Linked NPC name shown as clickable link on read-only character views

## v0.8.3
- Pulling strings catalog — game-level definitions with name, description, XP cost, and class category
- Characters select pulling strings from the catalog (filtered by class + general); AI category superuser-only
- Pulling string XP costs automatically counted in the experience tracker
- Creation allocation tracking — warns when character creation dots are unspent (attributes 5/4/3, skills 11/7/4, 3 specialisations, 7 merits)
- Auto XP calculation for attributes, skills, specialisations, and merits above creation baseline
- XP transfer from character to agency (1 character XP = 10 agency XP)
- MCP tools: list, create, update, delete pulling strings
- Pulling string catalog seeded with 12 entries (General, Fixer, Soldier)
- Django admin registration for PullingString model

## v0.8.2
- Class selection on character sheets and NPC dossiers — Fixer, Soldier, Science, Engineer, AI
- AI class restricted to superusers only
- Superusers can mark NPC dossier class as CLASSIFIED (hidden from players)

## v0.8.1
- Experience points tracking on character sheet — total XP, used XP, and auto-calculated remaining XP

## v0.8.0
- MCP API access — Bearer token authentication middleware for external tool integration (Claude Code, etc.)
- New `/api/status/` endpoint returning game state overview (version, game date, entity counts)
- MCP_API_TOKEN environment variable for secure API authentication

## v0.7.5
- Clickable base markers on the world map — navigates to the agency sheet and auto-expands/scrolls to that base
- Added 'New Americ' alias for Venezuela map matching

## v0.7.4
- Fix: country labels now placed at the mainland centroid instead of bounding box center — fixes France, Norway, etc. being labeled in Africa due to overseas territories

## v0.7.3
- Map now uses label-free tiles — no more real-world country names (Iran, Venezuela, etc.) on the map
- Tooltips show in-game names only (e.g. "Nova Judea / New Texas" instead of "Iran")

## v0.7.2
- Country name labels displayed on highlighted territories using the in-game name (e.g. "Nova Judea" not "Iran")
- Split territory support — when multiple agencies claim parts of the same country, shown with dashed border and multi-label
- Hidden/classified base coordinates no longer appear on the map for players
- Map aliases for New America (Venezuela), Nova Judea and New Texas (Iran)

## v0.7.1
- Clickable agency filter on the world map — toggle agencies to show/hide their territories and bases
- Fixed NPC agency default map color (was invisible on dark tiles)

## v0.7.0
- Interactive world map showing agency territories and base locations
- Agency territories defined by alliance countries — colored polygons on the map
- Bases can have latitude/longitude coordinates — shown as markers on the map
- Agencies have a configurable map color (color picker in the header, admin only)
- Dark-themed Leaflet map with CARTO tiles, tooltips, and agency legend
- MAP link added to navigation bar

## v0.6.17
- Agencies can be marked as hidden — hidden agencies are only visible to superusers
- Hidden agencies are filtered from agency list, council page, and API
- HIDDEN badge shown on agency list and sheet header for admins

## v0.6.16
- NPC dossiers now have full WoD 2.0 operative stats (attributes, skills, derived traits, health, mental load, merits, flaws) — visible and editable by superusers only

## v0.6.15
- Tactical dice roller now available on all agency pages

## v0.6.14
- Fix: missing database migration for hidden_sections field (caused agency load failure)

## v0.6.13
- Bases can be marked as hidden — hidden bases are only visible to superusers
- Individual base sections can be hidden from players: location type, location merits, space usage, facilities, workspaces, aviation units, and base defenses
- Admins see lock/eye toggle per section; hidden sections show CLASSIFIED to players

## v0.6.11
- Chairman and superusers can mark agencies as present/absent in the council members panel
- Quorum is now based on present agencies, not total members — quorum indicator shows present count
- Absent agencies appear dimmed with a gray dot; present agencies have a green dot
- Votes auto-resolve when all present members have voted (absent agencies don't block the vote)

## v0.6.10
- Council votes now update in real-time via WebSocket — all players see votes as they are cast without refreshing
- Status changes (call vote, emergency suspend, auto-resolve) also broadcast live to all connected clients

## v0.6.9
- Chairman (player or admin) can call a vote on proposals — changes status from "proposed" to "voting"
- Votes auto-resolve when all council members have voted — status changes to "active" (passed) or "repealed" (failed) with frozen vote record
- Chairman can emergency suspend an active vote — records all votes including "did not vote" entries
- UIC Charter updated: Article IV Section 1 now includes the chairman's emergency suspension power
- New "emergency_suspended" status with red styling and frozen vote display

## v0.6.8
- Council voting system: when a proposal enters "voting" status, member agencies can vote for, against, or abstain
- Superusers can cast votes on behalf of any agency; players vote for their own agency
- Live vote tally with progress bar showing for/against/abstain breakdown
- Quorum check (>50% of members must vote) and result calculation per charter rules
- Chairman tie-break: if votes are tied, the chairman's vote decides the outcome
- Votes and results persist and display on proposals that have been through voting

## v0.6.7
- Players can now edit the name, description, notes, and type on their own council proposals while in "proposed" status

## v0.6.6
- Superusers can edit the UIC Charter from the site settings page (Markdown editor)
- Charter content now stored in the database instead of a static file

## v0.6.5
- Players can withdraw their own council proposals while still in "proposed" status

## v0.6.4
- Council proposals: "Proposed By" is now an agency dropdown for superadmins, auto-set to the player's agency for players
- Players with an agency can create council proposals (proposedBy auto-filled)
- Chairman agency players can reorder council proposals via drag and drop

## v0.6.3
- Added COUNCIL link to the top navigation menu

## v0.6.2
- Superusers can now add or remove multiple successes at once on FTL projects per agency — input field replaces the old +1/−1 buttons

## v0.6.1
- Fixed linked dossier links on agency sheets being hard to read — added missing btn-cyber styling with cyan border, glow hover, and proper contrast on dark backgrounds

## v0.6.0
- Agency EXP section now shows available points (pool minus used) as the big number, with an admin button to add EXP
- Agency sheets display linked dossiers (characters from workspaces + NPC dossiers) with clickable links to their sheets
- Superusers can post as any character or NPC dossier in comms via a dropdown selector — messages show the dossier name with a PC/NPC badge
- NPC dossiers support a hidden flag — hidden dossiers are only visible to superusers, toggleable from the admin panel
- NPC dossiers without an agency now labelled UNAFFILIATED instead of NPC
- New dossier list filters: UNAFFILIATED and HIDDEN (admin-only)
- Hidden checkbox on NPC dossier creation dialog

## v0.5.5
- Fixed agency pages stuck on "DECRYPTING..." — syntax error in facility classification ternary prevented React from loading

## v0.5.4
- NPC agency bases now support the CLASSIFIED visibility system
- Admins can classify/declassify: entire bases section, individual bases, facilities, workspaces, and equipment per base
- Non-admin users see CLASSIFIED placeholders for hidden base data

## v0.5.3
- Facilities now use multi-select — pick any combination of options instead of a single level (barracks, armory, brig, medical, computer core, storage, aviation, etc.)
- Workspaces are now a separate section — can add multiple workspaces per base, each assignable to a character or NPC
- Workspace assignment dropdown shows characters and agency NPCs grouped by type

## v0.5.2
- Hover tooltips on all base elements — location types, merits, facilities, equipment, and collapsed base headers show descriptions on hover
- Fixed EXP sync between bases and core stats display

## v0.5.1
- Experience pool now shows used/total when bases are present (turns red when overspent)
- Added HR Off-boarding Office Suite 55 facility (Exp 5, Size 2)

## v0.5.0
- Added agency bases system — agencies can now have multiple bases with configurable locations, merits, facilities, and equipment
- Bases track EXP cost and space usage with a visual capacity bar
- Location types: Official Building, Estate, Military Base, Black Site
- Location merits: Armored, Underwater, Underground, Extra/Super Large, Front
- Facilities with levels: Aviation, Auditorium, Barracks, Armory, Brig, Medical, Computer Core, Storage, Workspace
- Facility equipment: Aviation units, Base defenses
- Admin settings page to configure all base options (prices, sizes, descriptions) — accessible from the agencies list
- Bases are purchased from the agency EXP pool

## v0.4.5
- Player dossier cards now show the owner's username (or "GM" for superadmins) on the contact dossiers list
- Fixed agency merits, flaws, and global flaws names getting cut off — columns now have minimum widths

## v0.4.4
- Added skill specialisations to operative character sheets — select a skill and name the specialisation (e.g., Firearms: Pistols)
- Specialisations panel with add/remove, auto-save, and read-only view for non-owners

## v0.4.3
- Redesigned favicon — overlapping EX monogram with white E and cyan X on dark navy

## v0.4.2
- Added favicon — cyan X with crosshair and corner brackets on dark navy, matching the BLACKLOG.NET theme

## v0.4.1
- Fixed notes columns in agency tables (assets, fleet, projects) getting cut off — now renders as resizable textareas

## v0.4.0
- Django admin user list now shows active status, last login, and staff/superuser columns
- Registration now requires admin approval — new accounts are created as inactive until a superuser activates them via Django admin
- Inactive users see "ACCOUNT PENDING" message on login instead of generic "invalid credentials"

## v0.3.6
- Registration now requires admin approval — new accounts are created as inactive until a superuser activates them via Django admin
- Inactive users see "ACCOUNT PENDING" message on login instead of generic "invalid credentials"

## v0.3.5
- Fixed lightbox clipping — image overlay now renders at document root via portal

## v0.3.4
- Image lightbox on dossier pages — clicking a portrait shows the full-size image in an overlay
- Edit overlay on detail page portrait — hovering the bottom of the image reveals an EDIT button for users with access

## v0.3.3
- Added explainer text on operatives page describing its purpose to players
- Fixed dossier names being cut off on list cards — names now wrap instead of truncating

## v0.3.2
- Dossier transfers — superusers can transfer dossiers between players, from player to agency (converts to NPC dossier), from agency to player (converts to player contact), and between agencies
- Player dossiers now show "BIFROST UNION" badge on the list page, matching how NPC dossiers display their agency
- Nationality flags on dossier list cards — flag emoji displayed under portrait based on nationality field

## v0.3.1
- Fixed occupation field too small on dossier detail page — now spans full grid width in both read-only and editable views
- Fixed occupation text truncated on dossier list cards — text now wraps instead of clipping

## v0.3.0
- Added NPC dossiers — admin-created dossiers that can be assigned to NPC agencies
- NPC dossiers are read-only for players; only admins can edit demographics, bio, state, and images
- Players can add, edit, and delete their own field notes on NPC dossiers (Markdown supported)
- NPC dossier creation dialog with agency selector (admin only)
- Agency badge displayed on NPC dossier cards in list view
- "NPC DOSSIERS" filter tab on contact dossiers list page
- Agency assignment module on NPC dossier detail page (admin can reassign)
- NPC dossier detail header shows type label and agency badge

## v0.2.2
- Fixed charter page blank — pinned marked.js to v14.1.4 (latest version removed marked.min.js)

## v0.2.1
- Fixed Interstellar Council link not visible to non-admin players on agency list page

## v0.2.0
- Added Global Flaws system — flaws that apply to all agencies, managed by superadmins
- Added FTL Projects system — global FTL travel research with per-agency progress tracking
- Added United Interstellar Council — agreements, initiatives, and laws visible on all agency sheets
- Council management page with filter tabs and inline editing (superadmin only)
- FTL project management page with pros/cons lists (superadmin only)
- Global flaws management page with inline editing (superadmin only)
- Agency sheets now display global flaws, FTL project assignments, and council items as read-only
- Admin navigation buttons for Global Flaws, FTL Projects, and Interstellar Council on agency list
- UIC council membership — agencies can be added to the council via checkbox on agency sheet
- UIC chairman designation — superusers can set the council chairman from the UIC page
- UIC council members panel on the council page showing all members and chairman
- UIC Charter document with formal articles covering membership, voting, quorum, chairman, enforcement, and amendments
- Charter page accessible from the UIC page, rendered with themed markdown
- UIC page now viewable by all logged-in players (editing remains superadmin only)
- Switched to manual version control (removed auto-increment on push)

## v0.1.25
- Rebranded from FOUNDATION to BLACKLOG.NET across all page titles, navigation, login screen, and boot sequence

## v0.1.14
- Fixed data loss when adding/removing list items while text input has pending changes
- Blur active input before add/remove to flush pending saves, then read from ref for fresh data
- Applied fix to AllianceModule, TableModule (agency sheet), ExpandableListModule, and InventoryModule (character sheet)

## v0.1.13
- Fluid typing: switched text inputs to uncontrolled (defaultValue) so React never overwrites typed text
- After 1.5s pause or clicking away: data saves directly to server in the background
- Separate quiet save path that never triggers page re-renders
- Debounced Lucide icon refresh to avoid per-render overhead
- Applied to both agency and character sheets

## v0.1.12
- Fixed alliance migration failure on production (existing string data now converted to JSON)

## v0.1.11
- Expanded alliance field into 3-column panel (countries, companies, organizations)
- Alliance section placed above notes with add/remove entries per column

## v0.1.10
- Fixed changelog versioning to always match the upcoming CI release

## v0.1.9
- Corrected changelog version numbers to match CI releases

## v0.1.7
- Fixed changelog not showing in Docker deployment (was excluded by .dockerignore)

## v0.1.6
- Hamburger menu for mobile navigation (collapses below 640px)

## v0.1.5
- Added version display with clickable changelog modal

## v0.1.4
- Added agencies feature for geopolitical organizations
- Player agency with change request workflow
- NPC agencies with per-field visibility (CLASSIFIED)
- Agency list dashboard and full agency sheet
- Added AGENCIES link to navigation

## v0.1.3
- Added HTTPS proxy settings for Nginx Proxy Manager

## v0.1.2
- Added WhiteNoise for static file serving in production

## v0.1.1
- Initial release
- Character (Operative) management system
- React-based character sheet with auto-save
- Dice roller (WoD 2.0 style)
- User authentication (login, register, profile)
