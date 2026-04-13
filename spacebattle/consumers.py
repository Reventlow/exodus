"""WebSocket consumer for spacebattle.

One group per battle id. Server-side action endpoints call
`broadcast_battle_event` to push updates; the consumer forwards them
to every connected client. Clients never send data up — they POST
mutations through the REST API and rely on the broadcast reply for
consistency.
"""

import json

from channels.generic.websocket import AsyncWebsocketConsumer


def battle_group_name(battle_id):
    return f"battle_{battle_id}"


class BattleConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        battle_id = self.scope["url_route"]["kwargs"]["battle_id"]
        self.battle_id = int(battle_id)
        self.group_name = battle_group_name(self.battle_id)

        user = self.scope.get("user", None)
        if user is None or not user.is_authenticated:
            await self.close()
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        # Client-sent messages are currently ignored; everything flows
        # through REST. Keep the handler so the socket stays open.
        pass

    async def battle_event(self, event):
        """Forward a group event to this connected client."""
        await self.send(text_data=json.dumps({
            "type": event.get("event_type", "event"),
            "payload": event.get("payload", {}),
        }))


def broadcast_battle_event(battle_id, event_type, payload):
    """Fan-out a single event to every viewer of a battle.

    Called from views.py after a mutating endpoint commits.
    """
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    layer = get_channel_layer()
    if layer is None:
        return
    async_to_sync(layer.group_send)(
        battle_group_name(battle_id),
        {
            "type": "battle_event",
            "event_type": event_type,
            "payload": payload,
        },
    )
