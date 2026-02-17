"""WebSocket URL routing for the comms application."""

from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r"ws/comms/$", consumers.CommsConsumer.as_asgi()),
]
