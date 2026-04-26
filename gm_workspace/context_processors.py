"""Context processors for the GM workspace."""
from .models import StoryIdea


def shared_briefs_count(request):
    """Expose GM_BRIEFS_UNREAD for the nav bar.

    Returns 0 for anonymous users and for superusers (GMs don't get the player
    BRIEFS link — they see the full GM workspace instead).

    For players: count of StoryIdea records shared with them. Drives whether
    the BRIEFS nav link appears at all, and the badge next to it.
    """
    if not request.user.is_authenticated or request.user.is_superuser:
        return {"GM_BRIEFS_COUNT": 0}
    count = StoryIdea.objects.filter(shared_with=request.user).distinct().count()
    return {"GM_BRIEFS_COUNT": count}
