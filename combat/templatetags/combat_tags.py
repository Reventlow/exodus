"""Custom template tags for the combat app.

v0.15.7 — surfaces a top-level COMBAT nav link to players who own at
least one Character that is currently a Participant in any encounter.
Superusers always see the link; anonymous users never do. The check
is one cheap EXISTS query per request (and only against a small
Participant table), so the cost is negligible compared to the rest
of the base.html context.

v0.15.18 — adds ``render_combat_dice`` which produces the per-row
dice + Gun Fu chip markup used by the encounter timeline. Reads the
``CombatLog.data`` JSONField directly (``dice`` and
``gun_fu_bonus_successes``) and is fully backwards-compatible with
legacy flat-int dice payloads via ``_normalize_dice_payload``.
"""

from django import template
from django.utils.safestring import mark_safe

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


@register.simple_tag
def render_combat_dice(entry):
    """Render the dice + Gun Fu chip markup for a single CombatLog entry.

    v0.15.18 — turns the ``data`` JSONField into the small inline span
    cluster shown beneath the message in the encounter TIMELINE table.
    Returns an empty string for entries that carry no dice payload
    (system rows, ``condition_set``, ``weapon_change``, etc.) — the
    caller still wraps the call in a ``{% if %}`` action-type guard,
    but defending here too keeps the tag safe to use anywhere.

    Reads from ``entry.data``:

      * ``dice`` — structured (v0.15.18+) OR legacy flat-int list.
        Normalised on the fly via ``_normalize_dice_payload``.
      * ``gun_fu_bonus_successes`` — int. When positive, an amber
        ``+N GUN FU`` chip is appended to the dice cluster.
      * ``d10`` — single int (the initiative branch). Renders one die
        without explosion / Gun Fu decoration since initiative is
        ``1d10 + modifier`` (no pool, no 10-again).

    Visual treatment (CSS classes, defined in encounter.html):

      * face 10 — ``die-ten`` — bold + glow on the explosion trigger.
      * face 8 / 9 — ``die-succ`` — solid primary, bold.
      * face 1..7 — ``die-fail`` — muted dim, half-opacity.
      * explode dice — ``die-explode`` — dashed border + ``↳``
        prefix so the chain is visually anchored to the parent.
      * Gun Fu chip — ``combat-die-gunfu`` — amber pill, distinct so
        die-derived successes can't be confused with merit successes.

    The late import of ``_normalize_dice_payload`` is deliberate —
    importing ``combat.views`` at module load time would cycle through
    the URL conf and the app registry on cold-start.
    """
    from combat.views import _normalize_dice_payload  # late import: avoids app-load cycle

    data = entry.data or {}

    # Initiative carries a single ``d10`` int instead of a pool — render
    # it as a one-die cluster with the same colour rules as a pool die.
    if entry.action_type == "initiative":
        d10 = data.get("d10")
        if isinstance(d10, int):
            succ = d10 >= 8
            if d10 == 10:
                cls = "die-ten"
            elif succ:
                cls = "die-succ"
            else:
                cls = "die-fail"
            return mark_safe(
                '<span class="combat-dice-row">'
                f'<span class="combat-die {cls}">{d10}</span>'
                '</span>'
            )
        return ""

    dice = _normalize_dice_payload(data.get("dice"))
    gun_fu = int(data.get("gun_fu_bonus_successes", 0) or 0)

    if not dice and gun_fu == 0:
        return ""

    parts = []
    for d in dice:
        face = d["face"]
        kind = d["kind"]
        succ = d["success"]
        # Class precedence: explode keeps its own class regardless of
        # face value (so a re-rolled 10 still reads as a chain link
        # rather than another trigger). Otherwise face 10 → die-ten,
        # successes → die-succ, failures → die-fail.
        if kind == "explode":
            cls = "die-explode"
        elif face == 10:
            cls = "die-ten"
        elif succ:
            cls = "die-succ"
        else:
            cls = "die-fail"
        prefix = "↳ " if kind == "explode" else ""
        parts.append(f'<span class="combat-die {cls}">{prefix}{face}</span>')

    if gun_fu > 0:
        parts.append(
            f'<span class="combat-die-gunfu">+{gun_fu} GUN FU</span>'
        )

    return mark_safe(
        '<span class="combat-dice-row">' + " ".join(parts) + "</span>"
    )
