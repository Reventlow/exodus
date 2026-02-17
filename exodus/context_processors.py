"""Custom context processors for Exodus."""

from pathlib import Path

from django.conf import settings


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
