"""
ASGI config for Exodus project.

Routes HTTP to Django and WebSocket to Channels consumers.
"""

import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "exodus.settings")

# Initialize Django ASGI application early to populate AppRegistry
django_asgi_app = get_asgi_application()

from comms.routing import websocket_urlpatterns as comms_ws  # noqa: E402
from agencies.routing import websocket_urlpatterns as council_ws  # noqa: E402
from spacebattle.routing import websocket_urlpatterns as battle_ws  # noqa: E402
from combat.routing import websocket_urlpatterns as combat_ws  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(URLRouter(comms_ws + council_ws + battle_ws + combat_ws))
        ),
    }
)
