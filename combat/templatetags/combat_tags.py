"""Custom template tags for the combat app.

v0.15.7 — surfaces a top-level COMBAT nav link to players who own at
least one Character that is currently a Participant in any encounter.
Superusers always see the link; anonymous users never do. The check
is one cheap EXISTS query per request (and only against a small
Participant table), so the cost is negligible compared to the rest
of the base.html context.
"""

from django import template

from combat.models import Participant


register = template.Library()


@register.simple_tag
def has_combat_visibility(user):
    """Return True if ``user`` should see the top-level COMBAT nav link.

    Visibility rule:
    * anonymous / unauthenticated → False (login link is shown instead).
    * superuser → True (the GM always wants the shortcut).
    * authenticated player → True iff they own a Character that's a
      Participant in any encounter (active, setup, or concluded — the
      detail page renders concluded encounters in read-only mode too,
      so historical access is preserved).
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    return Participant.objects.filter(character__owner=user).exists()
