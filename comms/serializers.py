"""
Serialization helpers for the comms application.

Manual JSON serialization (no DRF), following project conventions.
Uses Character model to build display names.
"""

from django.contrib.auth.models import User
from django.utils.timezone import localtime

from characters.models import Character

from .models import Message, Thread, ThreadMembership


def _get_display_name(user: User) -> str:
    """Return 'CharacterName (username)' or just username if no character."""
    character = Character.objects.filter(owner=user).first()
    if character:
        return f"{character.name} ({user.username})"
    return user.username


def serialize_message(message: Message) -> dict:
    """Serialize a single message."""
    return {
        "id": message.pk,
        "threadId": message.thread_id,
        "sender": {
            "id": message.sender_id,
            "displayName": _get_display_name(message.sender),
        },
        "content": message.content,
        "createdAt": localtime(message.created_at).isoformat(),
    }


def serialize_thread_summary(thread: Thread, user: User) -> dict:
    """Serialize a thread for the list view."""
    memberships = thread.memberships.select_related("user").all()
    members = [
        {"id": m.user_id, "displayName": _get_display_name(m.user)}
        for m in memberships
    ]

    # Last message preview
    last_msg = thread.messages.select_related("sender").order_by("-created_at").first()
    last_message = None
    if last_msg:
        last_message = {
            "sender": _get_display_name(last_msg.sender),
            "content": last_msg.content[:100],
            "createdAt": localtime(last_msg.created_at).isoformat(),
        }

    # Unread count for this user
    unread_count = 0
    try:
        membership = thread.memberships.get(user=user)
        unread_count = thread.messages.filter(
            created_at__gt=membership.last_read_at
        ).exclude(sender=user).count()
    except ThreadMembership.DoesNotExist:
        pass

    return {
        "id": thread.pk,
        "title": thread.title,
        "creator": thread.creator_id,
        "members": members,
        "lastMessage": last_message,
        "unreadCount": unread_count,
        "updatedAt": localtime(thread.updated_at).isoformat(),
    }


def serialize_thread_detail(thread: Thread, user: User) -> dict:
    """Serialize a thread with its recent messages."""
    summary = serialize_thread_summary(thread, user)
    messages = thread.messages.select_related("sender").order_by("created_at")[:100]
    summary["messages"] = [serialize_message(m) for m in messages]
    return summary
