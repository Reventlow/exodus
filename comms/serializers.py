"""
Serialization helpers for the comms application.

Manual JSON serialization (no DRF), following project conventions.
Uses Character model to build display names.
"""

from django.contrib.auth.models import User
from django.utils.timezone import localtime

from characters.models import Character
from npcs.models import NPC

from .models import Message, Thread, ThreadMembership


def _get_display_name(user: User) -> str:
    """Return 'CharacterName (username)' or just username if no character."""
    character = Character.objects.filter(owner=user).first()
    if character:
        return f"{character.name} ({user.username})"
    return user.username


def _serialize_member(user: User, membership: ThreadMembership | None = None) -> dict:
    """Serialize a thread member with display name and portrait.

    If the membership has an alias (GM/NPC persona), use that instead
    of the user's real character identity.
    """
    data = {"id": user.pk}

    # Check for alias on the membership
    if membership and membership.alias_type:
        if membership.alias_type == "gm":
            data["displayName"] = "GM"
            profile = getattr(user, "profile", None)
            data["portrait"] = profile.avatar.url if profile and profile.avatar else None
        elif membership.alias_type == "npc" and membership.alias_id:
            npc = NPC.objects.filter(pk=membership.alias_id).first()
            data["displayName"] = membership.alias_name or (npc.name if npc else "NPC")
            data["portrait"] = npc.image.url if npc and npc.image else None
        elif membership.alias_type == "character" and membership.alias_id:
            char = Character.objects.filter(pk=membership.alias_id).first()
            data["displayName"] = membership.alias_name or (char.name if char else "Character")
            data["portrait"] = char.profile_picture.url if char and char.profile_picture else None
        else:
            data["displayName"] = membership.alias_name or user.username
            data["portrait"] = None
        data["alias"] = {"type": membership.alias_type, "id": membership.alias_id, "name": membership.alias_name}
        return data

    # Default: use the user's character portrait, fall back to avatar
    character = Character.objects.filter(owner=user).first()
    if character:
        data["displayName"] = f"{character.name} ({user.username})"
        data["portrait"] = character.profile_picture.url if character.profile_picture else None
    else:
        data["displayName"] = user.username
        data["portrait"] = None

    # Fall back to user avatar if no character portrait
    if not data["portrait"]:
        profile = getattr(user, "profile", None)
        if profile and profile.avatar:
            data["portrait"] = profile.avatar.url

    return data


def serialize_message(message: Message) -> dict:
    """Serialize a single message."""
    data = {
        "id": message.pk,
        "threadId": message.thread_id,
        "sender": {
            "id": message.sender_id,
            "displayName": _get_display_name(message.sender),
        },
        "content": message.content,
        "image": message.image.url if message.image else None,
        "createdAt": localtime(message.created_at).isoformat(),
        "editedAt": localtime(message.edited_at).isoformat() if message.edited_at else None,
    }
    if message.posted_as_type and message.posted_as_name:
        data["postedAs"] = {
            "type": message.posted_as_type,
            "id": message.posted_as_id,
            "name": message.posted_as_name,
        }
    return data


def serialize_thread_summary(thread: Thread, user: User) -> dict:
    """Serialize a thread for the list view."""
    memberships = thread.memberships.select_related("user").all()
    # Filter out hidden members (shadow access from cyber terminal)
    visible = [m for m in memberships if not m.hidden]
    members = [_serialize_member(m.user, m) for m in visible]

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
        "isConnectionClosed": thread.is_connection_closed,
        "isIntercepted": ThreadMembership.objects.filter(thread=thread, user=user, hidden=True).exists(),
    }


def serialize_thread_detail(thread: Thread, user: User) -> dict:
    """Serialize a thread with its recent messages."""
    summary = serialize_thread_summary(thread, user)
    messages = thread.messages.select_related("sender").order_by("created_at")[:100]
    summary["messages"] = [serialize_message(m) for m in messages]
    return summary
