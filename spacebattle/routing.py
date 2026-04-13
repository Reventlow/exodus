"""WebSocket URL routing for the spacebattle application."""

from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r"ws/spacebattle/(?P<battle_id>\d+)/$", consumers.BattleConsumer.as_asgi()),
]
