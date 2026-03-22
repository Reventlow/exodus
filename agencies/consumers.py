"""WebSocket consumer for council vote live updates.

All authenticated users on the council page connect to ws://host/ws/council/.
When a vote is cast or status changes, the updated item is broadcast to all.
"""

import json

from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer


COUNCIL_GROUP = "council_votes"


class CouncilConsumer(WebsocketConsumer):
    """Broadcasts council item updates to all connected clients."""

    def connect(self):
        user = self.scope["user"]
        if not user.is_authenticated:
            self.close()
            return

        async_to_sync(self.channel_layer.group_add)(
            COUNCIL_GROUP, self.channel_name
        )
        self.accept()

    def disconnect(self, close_code):
        async_to_sync(self.channel_layer.group_discard)(
            COUNCIL_GROUP, self.channel_name
        )

    def council_update(self, event):
        """Forward an updated council item to the client."""
        self.send(text_data=json.dumps({
            "type": "council_update",
            "item": event["item"],
        }))
