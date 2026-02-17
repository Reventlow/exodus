"""
WebSocket consumer for the comms application.

Single connection per user at ws://host/ws/comms/.
Uses sync WebsocketConsumer (safe with SQLite).
"""

import json

from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer

from .models import ThreadMembership


class CommsConsumer(WebsocketConsumer):
    """Handles WebSocket connections for real-time messaging."""

    def connect(self):
        """Join user-specific group and all thread groups on connect."""
        user = self.scope["user"]
        if not user.is_authenticated:
            self.close()
            return

        self.user_group = f"user_{user.pk}"
        async_to_sync(self.channel_layer.group_add)(
            self.user_group, self.channel_name
        )

        # Join all thread groups the user is a member of
        self.thread_groups = set()
        memberships = ThreadMembership.objects.filter(user=user)
        for m in memberships:
            group = f"thread_{m.thread_id}"
            self.thread_groups.add(group)
            async_to_sync(self.channel_layer.group_add)(
                group, self.channel_name
            )

        self.accept()

    def disconnect(self, close_code):
        """Leave all groups on disconnect."""
        if hasattr(self, "user_group"):
            async_to_sync(self.channel_layer.group_discard)(
                self.user_group, self.channel_name
            )
        if hasattr(self, "thread_groups"):
            for group in self.thread_groups:
                async_to_sync(self.channel_layer.group_discard)(
                    group, self.channel_name
                )

    # -----------------------------------------------------------------------
    # Channel layer event handlers
    # -----------------------------------------------------------------------

    def chat_message(self, event):
        """Forward a new message to the client."""
        self.send(text_data=json.dumps({
            "type": "new_message",
            "message": event["message"],
        }))

    def unread_update(self, event):
        """Forward unread count update to the client."""
        self.send(text_data=json.dumps({
            "type": "unread_update",
            "threadId": event["thread_id"],
            "unreadCount": event["unread_count"],
        }))

    def membership_change(self, event):
        """Handle membership changes — join/leave thread groups."""
        thread_id = event["thread_id"]
        action = event["action"]
        group = f"thread_{thread_id}"

        if action == "added":
            self.thread_groups.add(group)
            async_to_sync(self.channel_layer.group_add)(
                group, self.channel_name
            )
        elif action == "removed":
            self.thread_groups.discard(group)
            async_to_sync(self.channel_layer.group_discard)(
                group, self.channel_name
            )

        self.send(text_data=json.dumps({
            "type": "membership_change",
            "threadId": thread_id,
            "action": action,
        }))
