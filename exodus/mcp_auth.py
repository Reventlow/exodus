"""Bearer token authentication middleware for MCP API access.

Allows external tools (like the Exodus MCP server) to authenticate
via Authorization: Bearer <token> header. When a valid token is
provided, the request is authenticated as a superuser and CSRF
checks are skipped.

Configure via MCP_API_TOKEN environment variable.
"""

import logging
import os

from django.http import JsonResponse

logger = logging.getLogger(__name__)

# Token loaded once at startup from environment
_MCP_TOKEN = os.environ.get("MCP_API_TOKEN", "")


class MCPTokenAuthMiddleware:
    """Authenticate API requests using a Bearer token.

    Must be placed AFTER AuthenticationMiddleware in MIDDLEWARE list.
    Only activates when an Authorization: Bearer header is present.
    Normal session-based auth is unaffected.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        if _MCP_TOKEN:
            logger.info("MCP token auth enabled")
        else:
            logger.info("MCP token auth disabled (MCP_API_TOKEN not set)")

    def __call__(self, request):
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.startswith("Bearer "):
            return self.get_response(request)

        # Token present — validate it
        if not _MCP_TOKEN:
            return JsonResponse(
                {"error": "MCP API token not configured on server."},
                status=503,
            )

        token = auth_header[7:]
        if token != _MCP_TOKEN:
            return JsonResponse(
                {"error": "Invalid API token."},
                status=401,
            )

        # Valid token — authenticate as superuser
        from django.contrib.auth.models import User

        superuser = User.objects.filter(is_superuser=True, is_active=True).first()
        if not superuser:
            return JsonResponse(
                {"error": "No active superuser found."},
                status=500,
            )

        request.user = superuser
        request._dont_enforce_csrf_checks = True
        return self.get_response(request)
