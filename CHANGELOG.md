# Changelog

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
