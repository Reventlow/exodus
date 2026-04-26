"""Custom context processors for Exodus."""

import logging
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)


def version(request):
    """Add the application version to template context."""
    version_file = Path(settings.BASE_DIR) / "version.txt"
    try:
        app_version = version_file.read_text().strip()
    except FileNotFoundError:
        app_version = "unknown"
    return {"APP_VERSION": app_version}


def changelog(request):
    """Add the changelog content to template context."""
    changelog_file = Path(settings.BASE_DIR) / "CHANGELOG.md"
    try:
        content = changelog_file.read_text().strip()
    except FileNotFoundError:
        content = "No changelog available."
    return {"CHANGELOG": content}


def game_date(request):
    """Add the next game session date to template context."""
    from .models import SiteSettings

    try:
        settings_obj = SiteSettings.objects.filter(pk=1).first()
        next_date = settings_obj.next_game_date if settings_obj else None
    except Exception:
        logger.exception("Failed to load SiteSettings")
        next_date = None
    return {"NEXT_GAME_DATE": next_date}


def impersonation(request):
    """Add impersonation flag to template context."""
    return {
        "IS_IMPERSONATING": bool(request.session.get("_impersonate_real_user_id")),
    }


def tweaks(request):
    """Expose SiteSettings.tweaks (palette, agency_name, etc.) globally.

    Wave 1 of the clearance-gate aesthetic rollout: ``base.html`` reads
    ``TWEAKS.palette`` to set ``<html data-palette="...">`` so the rest
    of the app inherits the same accent the login surface uses.

    Falls back to the model's default tweaks if SiteSettings is missing
    or the DB is unreachable, so template rendering never blows up.
    """
    from .models import SiteSettings

    try:
        settings_obj = SiteSettings.load()
        return {"TWEAKS": settings_obj.get_tweaks()}
    except Exception:
        logger.exception("Failed to load SiteSettings tweaks")
        return {"TWEAKS": SiteSettings.default_tweaks()}


def session_chrome(request):
    """Compute strip header values: codename, session id, ops-online count.

    All three feed the new ``base.html`` header strip. We compute them in
    one processor so we hit the ``UserProfile`` table at most once.
    Returns ``{}`` for unauthenticated requests so anonymous pages don't
    pay the query cost.
    """
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}

    user = request.user

    # Codename: superusers are "GM", players use their first character's
    # name, fall back to username uppercased, then "OPERATIVE".
    codename = "OPERATIVE"
    if user.is_superuser:
        codename = "GM"
    else:
        try:
            char = user.characters.first()
            if char and char.name and char.name != "UNKNOWN AGENT":
                codename = char.name.upper()
            elif user.username:
                codename = user.username.upper()
        except Exception:
            codename = (user.username or "OPERATIVE").upper()

    # Session ID: 8-char prefix of the Django session key (uppercased).
    ses = "—"
    try:
        key = request.session.session_key or ""
        if key:
            ses = key[:8].upper()
    except Exception:
        pass

    # OPS online: count of UserProfile.last_activity within the last 2h.
    # Cached in process for 30s — the count doesn't need to be fresh
    # per request and the ``UserProfile`` table is hit hard otherwise.
    ops_online = _ops_online_count()

    return {
        "STRIP_CODENAME": codename,
        "STRIP_SES": ses,
        "STRIP_OPS_ONLINE": ops_online,
    }


# Module-level cache for the OPS-online count (TTL 30s).
_OPS_CACHE = {"value": 0, "expires": 0.0}
_OPS_TTL_SEC = 30


def _ops_online_count():
    """Number of users whose ``UserProfile.last_activity`` is within 2h."""
    import time
    from datetime import timedelta

    now_ts = time.monotonic()
    if now_ts < _OPS_CACHE["expires"]:
        return _OPS_CACHE["value"]

    try:
        from django.contrib.auth.models import User
        from django.utils import timezone

        threshold = timezone.now() - timedelta(hours=2)
        count = User.objects.filter(
            is_active=True,
            profile__last_activity__gte=threshold,
        ).count()
    except Exception:
        logger.exception("Failed to compute OPS online count")
        count = 0

    _OPS_CACHE["value"] = count
    _OPS_CACHE["expires"] = now_ts + _OPS_TTL_SEC
    return count


def map_visibility(request):
    """Add map visibility settings to template context."""
    from .models import SiteSettings
    try:
        settings_obj = SiteSettings.objects.filter(pk=1).first()
        show_world = settings_obj.show_world_map if settings_obj else True
        show_star = settings_obj.show_star_map if settings_obj else False
        show_starships = settings_obj.show_starships if settings_obj else False
    except Exception:
        show_world = True
        show_star = False
        show_starships = False

    # City maps visible to this user
    city_maps = []
    try:
        from starmap.models import CityMap
        if hasattr(request, "user") and request.user.is_authenticated:
            if request.user.is_staff:
                city_maps = list(CityMap.objects.filter(enabled=True).values("id", "name"))
            else:
                city_maps = list(CityMap.objects.filter(enabled=True, visible_to_players=True).values("id", "name"))
    except Exception:
        pass

    # Nav labels and council
    try:
        if settings_obj is None:
            from .models import SiteSettings
            settings_obj = SiteSettings.objects.filter(pk=1).first()
        labels = {
            "NAV_DISPATCH": settings_obj.label_dispatch if settings_obj else "DISPATCH",
            "NAV_PLAYERS": settings_obj.label_players if settings_obj else "PLAYERS",
            "NAV_AGENCIES": settings_obj.label_agencies if settings_obj else "AGENCIES",
            "NAV_COUNCIL": settings_obj.label_council if settings_obj else "COUNCIL",
            "NAV_NPCS": settings_obj.label_npcs if settings_obj else "NPC'S",
            "NAV_COMMS": settings_obj.label_comms if settings_obj else "COMMS",
            "SHOW_COUNCIL": settings_obj.show_council if settings_obj else True,
        }
    except Exception:
        labels = {
            "NAV_DISPATCH": "DISPATCH", "NAV_PLAYERS": "PLAYERS",
            "NAV_AGENCIES": "AGENCIES", "NAV_COUNCIL": "COUNCIL",
            "NAV_NPCS": "NPC'S", "NAV_COMMS": "COMMS", "SHOW_COUNCIL": True,
        }

    return {
        "SHOW_WORLD_MAP": show_world,
        "SHOW_STAR_MAP": show_star,
        "SHOW_STARSHIPS": show_starships,
        "CITY_MAPS": city_maps,
        **labels,
    }
