# Changelog

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
