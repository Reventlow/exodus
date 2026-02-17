"""
Context processors for the comms application.

Provides unread message count to all templates for the nav badge.
"""

from .models import Message, ThreadMembership


def unread_count(request):
    """Add COMMS_UNREAD count to template context."""
    if not request.user.is_authenticated:
        return {"COMMS_UNREAD": 0}

    memberships = ThreadMembership.objects.filter(
        user=request.user
    ).select_related("thread")

    total = 0
    for m in memberships:
        total += Message.objects.filter(
            thread=m.thread,
            created_at__gt=m.last_read_at,
        ).exclude(sender=request.user).count()

    return {"COMMS_UNREAD": total}
