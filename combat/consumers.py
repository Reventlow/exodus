"""WebSocket consumer for the personal combat app.

One Channels group per encounter — name pattern ``combat_<id>``. Server
mutations call :func:`broadcast_combat_event` to fan-out a typed event;
the consumer forwards the event to every connected client. Clients
push mutations via REST (Phase 1+) and consume only the resulting
broadcast for a consistent state model.

Mirrors the spacebattle pattern but isolated under its own group prefix
so the two systems share no WS state.
"""

import json
import logging

from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer
from channels.layers import get_channel_layer


logger = logging.getLogger(__name__)


def broadcast_combat_event(encounter_id, event_type, payload):
    """Broadcast a single typed event to everyone in the encounter's group.

    Swallows channel-layer exceptions so a Redis outage cannot 500 the
    calling REST endpoint — REST still works, the UI degrades to a
    manual refresh. Matches the resilience contract spacebattle adopted
    in Release G.
    """
    try:
        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(
            f"combat_{encounter_id}",
            {"type": "combat.event", "event_type": event_type, "payload": payload},
        )
    except Exception:
        logger.exception("broadcast_combat_event failed for encounter %s", encounter_id)


class EncounterConsumer(WebsocketConsumer):
    """Per-encounter live channel.

    v0.15.7 — tightened authorisation. Subscription is granted to:

    * Superusers (the GM driving the combat) — any encounter.
    * Players whose Character is currently a Participant of the
      target encounter — only that encounter.

    Anyone else (anonymous, or an authenticated player with no
    character in this fight) is dropped at connect with WebSocket
    close code ``4403`` (analogous to HTTP 403). Bad / missing
    encounter id closes with ``4400``; missing auth with ``4401``.
    The check uses the ORM (the WS scope already injects the
    AuthMiddleware'd user), so it matches the exact same ownership
    semantics as the HTTP view layer.
    """

    def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            self.close(code=4401)
            return
        try:
            encounter_id = int(self.scope["url_route"]["kwargs"]["encounter_id"])
        except (KeyError, ValueError):
            self.close(code=4400)
            return

        # Authorisation:
        # - superusers can subscribe to any encounter;
        # - players can subscribe iff they own a Character in the
        #   encounter's participants list (mirrors the HTTP 403 check
        #   in encounter_page so WS visibility never widens the
        #   surface beyond the page view).
        if not user.is_superuser:
            # Local import to avoid an app-loading cycle: this module
            # is imported by combat/views.py at module load time.
            from .models import Participant
            is_participant = Participant.objects.filter(
                encounter_id=encounter_id,
                character__owner=user,
            ).exists()
            if not is_participant:
                self.close(code=4403)
                return

        self.encounter_id = encounter_id
        self.group_name = f"combat_{self.encounter_id}"
        async_to_sync(self.channel_layer.group_add)(self.group_name, self.channel_name)
        self.accept()

    def disconnect(self, code):
        if hasattr(self, "group_name"):
            async_to_sync(self.channel_layer.group_discard)(self.group_name, self.channel_name)

    def combat_event(self, event):
        """Forward a group message to the websocket as JSON."""
        self.send(text_data=json.dumps({
            "type": event.get("event_type", "unknown"),
            "payload": event.get("payload", {}),
        }))
