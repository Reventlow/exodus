# Exodus

Sci-fi tabletop RPG companion web app for a World of Darkness 2.0 campaign set in space. Players manage characters, agencies, communicate in-game, and participate in the United Interstellar Council (UIC). Hosted at exodus.blacklog.net, Docker image: elohite/exodus.

## Tech Stack

- **Backend:** Python 3.12, Django 5.1+, Daphne (ASGI), Channels 4+ with Redis
- **Database:** SQLite (file-based, mounted via Docker volume at /app/data)
- **Static files:** WhiteNoise, collected to `staticfiles/`
- **Real-time:** WebSockets via Django Channels + Redis channel layer
- **Images:** Pillow (character portraits, NPC portraits)
- **Deployment:** Docker + docker-compose, behind Nginx Proxy Manager with HTTPS
- **Frontend:** Django templates with HTMX for dynamic interactions, vanilla JS for WebSockets

## Django Apps

| App | Purpose |
|-----|---------|
| `exodus` | Core: site settings (singleton), game date, charter text, version/changelog context processors |
| `accounts` | User authentication (login, logout, registration) |
| `characters` | WoD 2.0 character sheets — attributes, skills, merits, flaws, health, inventory, mental load |
| `agencies` | Player/NPC agencies — attributes, council membership, voting, bases, FTL projects, global flaws, change requests |
| `comms` | In-game messaging — threads with membership, unread tracking, WebSocket real-time delivery, character/NPC impersonation |
| `npcs` | NPC management — dossiers, states (active/leave/missing/deceased), player notes |

## Key Domain Concepts

- **Agency:** A faction (player-controlled or NPC). Has attributes (power/finesse/resistance), bases, fleet, projects, and council membership.
- **UIC (United Interstellar Council):** Governance body. Members vote on proposals (agreements, initiatives, laws). Charter defines quorum, majority rules, chairman tie-breaks, emergency suspension.
- **Bases:** Installations belonging to agencies with configurable location types, merits, facilities (leveled), workspaces, and equipment. Costs/sizes defined in BaseConfig singleton.
- **FTL Projects:** Global research projects assigned to agencies with progress tracking (current_successes toward required_successes).
- **Global Flaws:** Flaws that apply to ALL agencies, managed by superusers.
- **Character sheets:** WoD 2.0 system — 9 attributes in power/finesse/resistance x mental/physical/social grid, 24 skills, derived stats.

## Role-Based Access

- **Superuser:** Full admin — manage all agencies, NPCs, council items, global flaws, FTL projects, base config, site settings, charter
- **Chairman:** Agency with `is_council_chairman=True` — can call votes, emergency suspend
- **Player:** Owns characters and belongs to a player agency — can vote, create proposals, send messages, manage own character

## Development

```bash
# Run locally
python manage.py runserver

# Run with Docker (dev)
docker-compose -f docker-compose.dev.yml up

# Run with Docker (prod)
docker-compose up -d

# Migrations
python manage.py makemigrations
python manage.py migrate
```

## Versioning

- Version stored in `version.txt` (e.g., `0.6.11`)
- All changes logged in `CHANGELOG.md`
- Docker image tagged as `elohite/exodus:<version>`
- Update both `version.txt` and `docker-compose.yml` image tag when releasing

## Project Conventions

- Templates live in `templates/<app_name>/` (project-level templates dir)
- URL routing: `exodus/urls.py` includes each app; comms, characters, agencies, npcs mount at root
- Singleton models (SiteSettings, BaseConfig) use `pk=1` enforcement and `load()` classmethod
- JSON fields used extensively for flexible data (attributes, skills, lists, alliance members)
- WebSocket consumers in `comms/consumers.py` and `agencies/consumers.py` with routing in `routing.py`
- Context processors provide version, changelog, game date, and unread message count globally
