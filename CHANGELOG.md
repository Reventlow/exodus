# Changelog

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
