"""WebSocket URL routing for the personal combat app."""

from django.urls import re_path

from . import consumers


websocket_urlpatterns = [
    re_path(r"ws/combat/(?P<encounter_id>\d+)/$", consumers.EncounterConsumer.as_asgi()),
]
