# Changelog

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
