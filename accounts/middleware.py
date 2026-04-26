"""Middleware for the accounts app."""

import logging

from django.utils import timezone

logger = logging.getLogger(__name__)

# Debounce: only update last_activity if the previous timestamp is at least
# this many seconds old. Limits DB writes when a user is actively clicking,
# typing, or polling without losing activity-monitoring fidelity.
DEBOUNCE_SECONDS = 30

# Auto-logout threshold. If a user's last_activity is older than this,
# their session is invalidated on their next request — they appear in the
# roster as INACTIVE and have to re-authenticate. Matches the activity-
# status spec: 2 hours / 4 hours / 2 days / INACTIVE.
INACTIVE_LOGOUT_SECONDS = 2 * 24 * 60 * 60

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
        # Pre-process: if the user has been inactive past the cutoff, log
        # them out BEFORE the view runs. They get the same treatment as
        # any anonymous request from this point on (likely → /login/).
        try:
            self._maybe_logout_inactive(request)
        except Exception:
            logger.exception("LastActivityMiddleware: logout check failed")

        response = self.get_response(request)

        # Post-process: refresh the timestamp on a successful authenticated
        # round-trip. Done in the response phase to keep request latency
        # untouched.
        try:
            self._maybe_touch(request)
        except Exception:
            logger.exception("LastActivityMiddleware: touch failed")
        return response

    @staticmethod
    def _is_excluded(request):
        """True if the request is not a human authenticated action."""
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return True
        # MCP API auth synthesises a superuser via Bearer token; skip those.
        if request.META.get("HTTP_AUTHORIZATION", "").startswith("Bearer "):
            return True
        path = getattr(request, "path", "") or ""
        if path.startswith(_SKIP_PREFIXES):
            return True
        return False

    @classmethod
    def _maybe_logout_inactive(cls, request):
        """Log out users whose last_activity is older than the cutoff,
        OR whose ``User.is_active`` flag has been cleared (burned —
        operative removed from the roster).
        """
        if cls._is_excluded(request):
            return
        from accounts.models import UserProfile
        from django.contrib.auth import logout

        # Burned operative — boot them on their next request even if their
        # session cookie is still valid. Belt-and-braces: ``is_active``
        # already prevents fresh logins; this also kicks the existing one.
        if not request.user.is_active:
            logout(request)
            return

        profile = UserProfile.objects.filter(user=request.user).only(
            "last_activity",
        ).first()
        if profile is None or profile.last_activity is None:
            return
        if (timezone.now() - profile.last_activity).total_seconds() > INACTIVE_LOGOUT_SECONDS:
            logout(request)

    @classmethod
    def _maybe_touch(cls, request):
        if cls._is_excluded(request):
            return

        # Imported lazily to avoid AppRegistry-not-ready issues at import time.
        from accounts.models import UserProfile

        now = timezone.now()
        profile = UserProfile.objects.filter(user=request.user).only(
            "id", "last_activity",
        ).first()
        if profile is None:
            # First-time visitor — create with the timestamp set.
            UserProfile.objects.get_or_create(
                user=request.user, defaults={"last_activity": now},
            )
            return
        prev = profile.last_activity
        if prev is None or (now - prev).total_seconds() >= DEBOUNCE_SECONDS:
            UserProfile.objects.filter(pk=profile.pk).update(last_activity=now)
