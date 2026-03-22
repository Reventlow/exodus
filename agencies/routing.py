"""WebSocket URL routing for the agencies application (council votes)."""

from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r"ws/council/$", consumers.CouncilConsumer.as_asgi()),
]
