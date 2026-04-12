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


def map_visibility(request):
    """Add map visibility settings to template context."""
    from .models import SiteSettings
    try:
        settings_obj = SiteSettings.objects.filter(pk=1).first()
        show_world = settings_obj.show_world_map if settings_obj else True
        show_star = settings_obj.show_star_map if settings_obj else False
    except Exception:
        show_world = True
        show_star = False

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
        "CITY_MAPS": city_maps,
        **labels,
    }
