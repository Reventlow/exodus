"""Middleware for the accounts app."""

import logging

from django.utils import timezone

logger = logging.getLogger(__name__)

# Debounce: only update last_activity if the previous timestamp is at least
# this many seconds old. Limits DB writes when a user is actively clicking,
# typing, or polling without losing activity-monitoring fidelity.
DEBOUNCE_SECONDS = 30

# Skip these path prefixes — static / media file requests don't represent
# user-initiated actions worth monitoring, and they can fire in bursts that
# would otherwise overwhelm the debounce.
_SKIP_PREFIXES = ("/static/", "/media/")


class LastActivityMiddleware:
    """Update ``UserProfile.last_activity`` for authenticated human requests.

    Runs in the response phase so it never adds latency to the request
    itself. Skipped silently for:

      - Anonymous users (no authenticated session).
      - MCP API requests authenticated via Bearer token (synthetic
        superuser, not a human acting on the site).
      - Static / media paths.
      - Users without a ``UserProfile`` row yet — created with the
        timestamp set on first visit.

    Errors are caught and logged so a flaky DB connection cannot 500 a
    page just because the activity touch failed.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            self._maybe_touch(request)
        except Exception:
            logger.exception("LastActivityMiddleware: touch failed")
        return response

    @staticmethod
    def _maybe_touch(request):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return
        # MCP API auth synthesises a superuser via Bearer token; skip those.
        if request.META.get("HTTP_AUTHORIZATION", "").startswith("Bearer "):
            return
        path = getattr(request, "path", "") or ""
        if path.startswith(_SKIP_PREFIXES):
            return

        # Imported lazily to avoid AppRegistry-not-ready issues at import time.
        from accounts.models import UserProfile

        now = timezone.now()
        profile = UserProfile.objects.filter(user=user).only(
            "id", "last_activity",
        ).first()
        if profile is None:
            # First-time visitor — create with the timestamp set.
            UserProfile.objects.get_or_create(
                user=user, defaults={"last_activity": now},
            )
            return
        prev = profile.last_activity
        if prev is None or (now - prev).total_seconds() >= DEBOUNCE_SECONDS:
            UserProfile.objects.filter(pk=profile.pk).update(last_activity=now)
