# Exodus

A sci-fi tabletop-RPG companion web app for a **World of Darkness 2.0** campaign set in space. Players manage characters and agencies, run starship operations, scan the star map, communicate in-game, and govern through the **United Interstellar Council (UIC)**. The GM runs the world from a dedicated workspace.

- **Live:** https://exodus.blacklog.net
- **Image:** `elohite/exodus` on Docker Hub
- **Docs:** [Architecture](architecture.md) · [Decision records (ADRs)](docs/adr/) · [Changelog](CHANGELOG.md) · [UIC Charter](UIC_CHARTER.md)

---

## Quick start

### Local (dev)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver          # http://127.0.0.1:8000
```

Real-time features (comms, live combat/agency updates) need **Redis** for the Channels layer:

```bash
docker run -p 6379:6379 redis        # or: docker-compose -f docker-compose.dev.yml up
```

### Docker

```bash
docker-compose -f docker-compose.dev.yml up      # dev
docker-compose up -d                              # prod-style (behind Nginx Proxy Manager + HTTPS)
```

The SQLite database and uploaded media are persisted via volumes (`/app/data`, `/app/media`).

---

## Tech stack

| Layer | Choice |
|-------|--------|
| Language / framework | Python 3.12, Django 5.1+ |
| Server | Daphne (ASGI) |
| Real-time | Django Channels 4+ over Redis (WebSockets) |
| Database | SQLite (single file, Docker volume at `/app/data`) — see [ADR-0001](docs/adr/0001-sqlite-single-file-database.md) |
| Static files | WhiteNoise (`collectstatic` → `staticfiles/`) |
| Images | Pillow (character/NPC portraits) |
| Frontend | Django templates + HTMX; vanilla JS for WebSockets; React 18 + in-browser Babel (**pinned to v7**) for interactive pages — see [ADR-0002](docs/adr/0002-in-browser-babel-pinned-v7.md) |
| Deploy | Docker + docker-compose, behind Nginx Proxy Manager, on ZimaOS |

---

## Project map

Django apps (templates live in the project-level `templates/<app>/`; most apps mount at root in `exodus/urls.py`):

| App | Purpose |
|-----|---------|
| `exodus` | Core: `SiteSettings`/`BaseConfig` singletons, game date, charter, version/changelog context processors, **MCP bearer auth** |
| `accounts` | Authentication (login, logout, registration) |
| `characters` | WoD 2.0 character sheets — attributes, skills, merits, flaws, health, inventory, mental load |
| `agencies` | Factions — attributes, bases & facilities, fleet, FTL projects, council membership/voting, global flaws, change requests |
| `comms` | In-game messaging — threads, unread tracking, WebSocket delivery, character/NPC impersonation |
| `npcs` | NPC dossiers, states, player notes |
| `combat` | WoD 2.0 personal/tactical combat — encounters, initiative, conditions, real-time via WebSocket |
| `starships` | Ship types/modules/classes, fleets, hulls, **FTL jumps** (see [ADR-0004](docs/adr/0004-ftl-jump-economy.md)) |
| `spacebattle` | Tactical space-battle maps and resolution |
| `starmap` | 3D star map (Three.js), **star-intel scanning** (see [ADR-0003](docs/adr/0003-star-intel-scanning-model.md)), public record, resources, claims |
| `gm_workspace` | GM-only tools at `/gm/` — story ideas, timeline, campaign log, star-intel oversight; player briefs at `/my-briefs/` |
| `news` | "Bifrost Dispatch" in-game news feed |

Key conventions: singletons use `pk=1` + a `load()` classmethod; JSON fields hold flexible per-entity data; WebSocket consumers + routing live in each real-time app; context processors expose version/changelog/game-date/unread-count globally. See [`CLAUDE.md`](CLAUDE.md) for the full conventions list.

---

## Testing

```bash
python manage.py test                 # full suite (~150 tests)
python manage.py test starmap         # one app
python manage.py check                # system checks
```

Most tests are plain `TestCase`/`Client` and need no services. A small number of WebSocket/Channels tests require a running **Redis** (they error with a connection refused if it's absent — that's environmental, not a failure of the code under test). CI runs the full suite with Redis available.

---

## Deployment & versioning

Releases are cut from the working tree and tracked in three files that move together:

1. `version.txt` — the canonical version (e.g. `0.15.57`)
2. `docker-compose.yml` — the `elohite/exodus:<version>` image tag
3. `CHANGELOG.md` — an entry for every release

On push to `main`, CI ("Docker Image CI/CD") runs the test suite + migrations on a fresh DB, builds and pushes `elohite/exodus:<version.txt>`, then commits the compose tag back. The image is deployed to ZimaOS. See [ADR-0005](docs/adr/0005-version-pinned-cdn-dependencies.md) on why front-end CDN deps are version-pinned.

> The working tree is the source of truth; git HEAD can lag production. Stage release files explicitly — never `git add -A`.

---

## GM access via MCP

`exodus/mcp_auth.py` adds bearer-token auth: a request with `Authorization: Bearer <MCP_API_TOKEN>` is authenticated as a superuser (CSRF-exempt), letting the companion `exodus-mcp` server query and edit live game data over the REST API. See [ADR-0006](docs/adr/0006-mcp-bearer-token-auth.md).
