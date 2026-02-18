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
