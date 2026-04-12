"""
Views for the comms (in-game messaging) application.

Provides API endpoints for thread management and messaging,
plus the page view that renders the React SPA.
"""

import json

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from characters.models import Character
from npcs.models import NPC

from .models import Message, Thread, ThreadMembership
from .serializers import (
    _get_display_name,
    _serialize_member,
    serialize_message,
    serialize_thread_detail,
    serialize_thread_summary,
)


# ---------------------------------------------------------------------------
# Page view
# ---------------------------------------------------------------------------


@login_required
def comms_index(request):
    """Render the comms SPA template."""
    return render(request, "comms/index.html")


# ---------------------------------------------------------------------------
# Thread list / create
# ---------------------------------------------------------------------------


@login_required
@require_http_methods(["GET", "POST"])
def thread_list(request):
    """List user's threads or create a new thread."""
    if request.method == "GET":
        if request.user.is_staff:
            threads = Thread.objects.all()
        else:
            thread_ids = ThreadMembership.objects.filter(
                user=request.user
            ).values_list("thread_id", flat=True)
            threads = Thread.objects.filter(pk__in=thread_ids)

        threads = threads.order_by("-updated_at")
        data = [serialize_thread_summary(t, request.user) for t in threads]
        return JsonResponse(data, safe=False)

    # POST: create thread
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    title = body.get("title", "").strip()
    member_ids = body.get("members", [])

    if not isinstance(member_ids, list):
        return JsonResponse({"error": "members must be a list"}, status=400)

    thread = Thread.objects.create(title=title, creator=request.user)

    # Always add creator as member, with optional persona alias
    alias_kwargs = {}
    if request.user.is_superuser:
        alias_type = body.get("aliasType", "")
        alias_id = body.get("aliasId")
        alias_name = body.get("aliasName", "")
        if alias_type:
            alias_kwargs = {
                "alias_type": alias_type,
                "alias_id": alias_id if alias_type in ("npc", "character") else None,
                "alias_name": alias_name,
            }
    ThreadMembership.objects.create(thread=thread, user=request.user, **alias_kwargs)

    # Add other members
    for uid in member_ids:
        if uid != request.user.pk:
            try:
                user = User.objects.get(pk=uid)
                ThreadMembership.objects.create(thread=thread, user=user)
                _notify_membership_change(thread, user, "added")
            except User.DoesNotExist:
                continue

    # NPC participant (GM feature): add a system user aliased as the NPC
    npc_participant = body.get("npcParticipant")
    if npc_participant and request.user.is_superuser:
        system_user, _ = User.objects.get_or_create(
            username="__system__",
            defaults={"is_active": False},
        )
        ThreadMembership.objects.create(
            thread=thread,
            user=system_user,
            alias_type=npc_participant.get("type", "npc"),
            alias_id=npc_participant.get("id"),
            alias_name=npc_participant.get("name", "NPC"),
        )

    data = serialize_thread_detail(thread, request.user)
    return JsonResponse(data, status=201)


# ---------------------------------------------------------------------------
# Thread detail
# ---------------------------------------------------------------------------


@login_required
@require_http_methods(["GET", "PUT"])
def thread_detail(request, thread_id):
    """Get thread detail with messages, or update title (superuser PUT)."""
    thread = get_object_or_404(Thread, pk=thread_id)
    if not _can_view_thread(request.user, thread):
        return JsonResponse({"error": "Forbidden"}, status=403)

    if request.method == "PUT":
        if not request.user.is_superuser:
            return JsonResponse({"error": "Forbidden"}, status=403)
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        if "title" in body:
            thread.title = body["title"]
            thread.save(update_fields=["title"])
        return JsonResponse(serialize_thread_detail(thread, request.user))

    data = serialize_thread_detail(thread, request.user)
    return JsonResponse(data)


@login_required
@require_POST
def update_alias(request, thread_id):
    """Update the current user's display alias in a thread. Superuser only."""
    if not request.user.is_superuser:
        return JsonResponse({"error": "Forbidden"}, status=403)
    thread = get_object_or_404(Thread, pk=thread_id)
    try:
        membership = ThreadMembership.objects.get(thread=thread, user=request.user)
    except ThreadMembership.DoesNotExist:
        return JsonResponse({"error": "Not a member"}, status=400)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    alias_type = body.get("aliasType", "")
    if alias_type == "self" or not alias_type:
        membership.alias_type = ""
        membership.alias_id = None
        membership.alias_name = ""
    else:
        membership.alias_type = alias_type
        membership.alias_id = body.get("aliasId") if alias_type in ("npc", "character") else None
        membership.alias_name = body.get("aliasName", "")
    membership.save(update_fields=["alias_type", "alias_id", "alias_name"])

    return JsonResponse({"status": "ok"})


@login_required
@require_http_methods(["DELETE"])
def delete_thread(request, thread_id):
    """Delete a thread. Superuser only."""
    if not request.user.is_superuser:
        return JsonResponse({"error": "Forbidden"}, status=403)
    thread = get_object_or_404(Thread, pk=thread_id)
    thread.delete()
    return JsonResponse({"status": "deleted"})


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


@login_required
@require_POST
def send_message(request, thread_id):
    """Send a message to a thread and broadcast via WebSocket."""
    thread = get_object_or_404(Thread, pk=thread_id)
    if not _can_view_thread(request.user, thread):
        return JsonResponse({"error": "Forbidden"}, status=403)
    if thread.is_connection_closed:
        return JsonResponse({"error": "Connection closed"}, status=400)
    if not request.user.is_superuser:
        from exodus.models import SiteSettings
        if SiteSettings.load().lock_comms:
            return JsonResponse({"error": "Comms are locked between sessions."}, status=403)

    # Support both JSON and multipart (for image uploads)
    image = None
    if request.content_type and "multipart" in request.content_type:
        content = request.POST.get("content", "").strip()
        image = request.FILES.get("image")
        body = request.POST
    else:
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        content = body.get("content", "").strip()

    if not content and not image:
        return JsonResponse({"error": "Content or image is required"}, status=400)

    # Superusers can post as GM (default), a character, or NPC dossier
    posted_as_type = ""
    posted_as_id = None
    posted_as_name = ""
    if request.user.is_superuser:
        pa_type = body.get("postedAsType", "gm")
        pa_id = body.get("postedAsId")
        if pa_type == "gm" or (not pa_type and not pa_id):
            posted_as_type = "gm"
            posted_as_id = None
            posted_as_name = "GM"
        elif pa_type == "self":
            pass  # Leave posted_as fields empty — posts as own user
        elif pa_type == "character" and pa_id:
            try:
                char = Character.objects.only("id", "name").get(pk=pa_id)
                posted_as_type = "character"
                posted_as_id = char.id
                posted_as_name = char.name
            except Character.DoesNotExist:
                pass
        elif pa_type == "npc" and pa_id:
            try:
                npc = NPC.objects.only("id", "name").get(pk=pa_id)
                posted_as_type = "npc"
                posted_as_id = npc.id
                posted_as_name = npc.name
            except NPC.DoesNotExist:
                pass

    message = Message.objects.create(
        thread=thread,
        sender=request.user,
        content=content,
        image=image,
        posted_as_type=posted_as_type,
        posted_as_id=posted_as_id,
        posted_as_name=posted_as_name,
    )

    # Touch thread updated_at
    thread.updated_at = timezone.now()
    thread.save(update_fields=["updated_at"])

    # Mark as read for sender
    ThreadMembership.objects.filter(
        thread=thread, user=request.user
    ).update(last_read_at=timezone.now())

    # Broadcast message via channel layer
    msg_data = serialize_message(message)
    channel_layer = get_channel_layer()

    # Send to all thread members
    memberships = thread.memberships.select_related("user").all()
    for membership in memberships:
        async_to_sync(channel_layer.group_send)(
            f"user_{membership.user_id}",
            {
                "type": "chat.message",
                "message": msg_data,
            },
        )

    # Send unread updates to all members except sender
    for membership in memberships:
        if membership.user_id != request.user.pk:
            unread = thread.messages.filter(
                created_at__gt=membership.last_read_at
            ).exclude(sender=membership.user).count()
            async_to_sync(channel_layer.group_send)(
                f"user_{membership.user_id}",
                {
                    "type": "unread.update",
                    "thread_id": thread.pk,
                    "unread_count": unread,
                },
            )

    return JsonResponse(msg_data, status=201)


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------


@login_required
@require_POST
def add_member(request, thread_id):
    """Add a member to a thread. Only owner or admin."""
    thread = get_object_or_404(Thread, pk=thread_id)
    if not (request.user == thread.creator or request.user.is_staff):
        return JsonResponse({"error": "Forbidden"}, status=403)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    user_id = body.get("userId")
    if not user_id:
        return JsonResponse({"error": "userId is required"}, status=400)

    user = get_object_or_404(User, pk=user_id)
    _, created = ThreadMembership.objects.get_or_create(thread=thread, user=user)

    if created:
        _notify_membership_change(thread, user, "added")

    return JsonResponse({"status": "ok", "created": created})


@login_required
@require_http_methods(["DELETE"])
def remove_member(request, thread_id, user_id):
    """Remove a member from a thread. Owner/admin/self."""
    thread = get_object_or_404(Thread, pk=thread_id)
    target_user = get_object_or_404(User, pk=user_id)

    # Creator cannot be removed
    if target_user == thread.creator:
        return JsonResponse({"error": "Cannot remove the thread creator"}, status=400)

    # Permission: owner, admin, or self (leaving)
    is_owner = request.user == thread.creator
    is_admin = request.user.is_staff
    is_self = request.user == target_user

    if not (is_owner or is_admin or is_self):
        return JsonResponse({"error": "Forbidden"}, status=403)

    deleted, _ = ThreadMembership.objects.filter(
        thread=thread, user=target_user
    ).delete()

    if deleted:
        _notify_membership_change(thread, target_user, "removed")

    return JsonResponse({"status": "ok"})


@login_required
@require_POST
def admin_join(request, thread_id):
    """Admin force-join a thread."""
    if not request.user.is_staff:
        return JsonResponse({"error": "Forbidden"}, status=403)

    thread = get_object_or_404(Thread, pk=thread_id)
    _, created = ThreadMembership.objects.get_or_create(
        thread=thread, user=request.user
    )

    if created:
        _notify_membership_change(thread, request.user, "added")

    return JsonResponse({"status": "ok", "created": created})


# ---------------------------------------------------------------------------
# Read / Unread
# ---------------------------------------------------------------------------


@login_required
@require_POST
def mark_read(request, thread_id):
    """Mark a thread as read for the current user."""
    thread = get_object_or_404(Thread, pk=thread_id)
    now = timezone.now()
    updated = ThreadMembership.objects.filter(
        thread=thread, user=request.user
    ).update(last_read_at=now)

    if not updated:
        return JsonResponse({"error": "Not a member"}, status=403)

    return JsonResponse({"status": "ok"})


@login_required
@require_GET
def unread_count(request):
    """Get total unread message count across all threads."""
    count = _get_total_unread(request.user)
    return JsonResponse({"unreadCount": count})


# ---------------------------------------------------------------------------
# User list
# ---------------------------------------------------------------------------


@login_required
@require_GET
def user_list(request):
    """List all users for the member picker."""
    users = User.objects.filter(is_active=True).order_by("username")
    data = [_serialize_member(u) for u in users]
    return JsonResponse(data, safe=False)


@login_required
@require_GET
def dossier_list(request):
    """List all characters and NPCs for the 'post as' picker. Superuser only."""
    if not request.user.is_superuser:
        return JsonResponse({"error": "Forbidden"}, status=403)
    characters = [
        {"type": "character", "id": c.id, "name": c.name}
        for c in Character.objects.all().order_by("name").only("id", "name")
    ]
    npcs = [
        {"type": "npc", "id": n.id, "name": n.name}
        for n in NPC.objects.all().order_by("name").only("id", "name")
    ]
    return JsonResponse(characters + npcs, safe=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _can_view_thread(user: User, thread: Thread) -> bool:
    """Check if a user can view a thread."""
    if user.is_staff:
        return True
    return ThreadMembership.objects.filter(thread=thread, user=user).exists()


def _get_total_unread(user: User) -> int:
    """Count total unread messages across all threads for a user."""
    memberships = ThreadMembership.objects.filter(user=user).select_related("thread")
    total = 0
    for m in memberships:
        total += Message.objects.filter(
            thread=m.thread,
            created_at__gt=m.last_read_at,
        ).exclude(sender=user).count()
    return total


def _notify_membership_change(thread: Thread, user: User, action: str):
    """Notify a user about membership changes via WebSocket."""
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"user_{user.pk}",
        {
            "type": "membership.change",
            "thread_id": thread.pk,
            "action": action,
        },
    )
