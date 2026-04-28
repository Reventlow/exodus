"""Views for the personal combat app.

v0.15.5 — full WoD 2.0 attack loop. Layers wound penalties, damage
track upgrade rules, conditions / stances, willpower spend, and the
defensive Full Defense / Dodge actions on top of the v0.15.4 attack
pipeline.

Attack pipeline (v0.15.5):

1. Compose the attacker's pool —
   ``Dexterity + chosen weapon skill + weapon dice modifier + GM
   modifier`` for character / NPC, or ``mook_combat_pool + GM
   modifier`` for mooks. **Plus** wound penalty (`-1 / -2 / -3` on
   the rightmost three filled health boxes), the sum of active
   condition attack modifiers, and `+3` if the attacker spends a
   willpower point (clamps at `willpower_current >= 1`).
2. Compute the target's defense — ``min(Dex, Wits) + Athletics`` for
   character / NPC, ``mook_defense`` for mooks. ``defense_override``
   wins if set. **Plus** condition defense modifiers. Special cases:
   ``incapacitated`` → 0 defense; ``defense_full`` → baseline
   doubled; ``dodging:N`` → N successes replace baseline.
3. Apply cover — ``light=-2``, ``heavy=-4``, ``full`` blocks the
   shot entirely (logged ``outcome="blocked_by_cover"``).
4. Floor the dice pool at ``0`` and roll — ``_roll_pool`` reuses the
   ``secrets`` source from initiative; 8/9/10 are successes, 10s
   "explode" and re-roll up to five recursion levels deep so the
   pathological all-tens case can't run away.
5. On any successes, compute damage — ``successes + weapon damage``,
   minus armor (``B`` track or ``L`` track from ``"B/L"`` rating;
   aggravated bypasses armor). Apply through ``_apply_damage`` which
   honours the WoD 2.0 track upgrade ladder
   (B → L → A): lethal overflow upgrades a bashing box per point,
   aggravated overflow upgrades a bashing then lethal box per point.
6. If the total damage now equals or exceeds ``health_max`` the
   target is auto-tagged ``incapacitated`` and a separate
   ``condition_set`` log row fires.
7. Append two log rows on a hit: ``attack`` (the resolution payload)
   and ``health_change`` (so the timeline can be filtered down to
   damage-only events). Misses write a single ``attack`` row.

Conditions (v0.15.5) live as a list of strings on
``participant.conditions``. Hardcoded vocabulary: ``prone``,
``stunned``, ``blinded``, ``grappled``, ``incapacitated``,
``defense_full``, ``dodging:N``, ``dodge_pending``. ``dodging:N``
encodes the dodge pool's success count without a schema change.
Defensive stances (``defense_full``, ``dodging:*``) auto-clear at
the round boundary in ``next_turn``.

This release is still **GM-only** — the player-facing surface lands
in v0.15.6 with the WebSocket fan-out. Faction is decorative; the
target picker offers every other participant in the encounter so
PvP works out of the box.

Initiative model (unchanged from v0.15.3):

* **Character / NPC** — ``modifier = Dexterity (attributes.finesse.physical)
  + Composure (attributes.resistance.social)``. Roll 1d10. Score is
  ``modifier + d10``. KeyError / TypeError / ValueError on partial
  sheets fall back to modifier ``0``.
* **Mook** — ``modifier = mook_combat_pool // 2``. Roll 1d10. Same
  score math.

Tiebreak is deterministic by participant id (lower id first).

Three participant kinds are supported (see v0.15.2 docs):

* ``character`` — links to a player :class:`characters.Character`.
* ``npc``       — links to an :class:`npcs.NPC` dossier (filtered to
                  full NPCs, not GM dossiers).
* ``mook``      — snapshot from the
                  :class:`exodus.SiteSettings` ``combat_npcs``
                  catalogue. Catalogue entries are denormalised at
                  spawn so later catalogue edits do not mutate
                  in-flight encounters.

CombatLog action types in use as of v0.15.5: ``initiative``,
``turn_advance``, ``round_advance``, ``system``, ``attack``,
``health_change``, ``weapon_change``, ``armor_change``,
``cover_change``, ``condition_set``, ``condition_clear``,
``willpower_change``, ``full_defense``, ``dodge``. Real-time fan-out
(WebSocket broadcast) lands in v0.15.6.
"""

import json
import secrets

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import F, Max
from django.http import (
    HttpResponseForbidden,
    HttpResponseNotAllowed,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_http_methods

from characters.models import Character
from exodus.models import SiteSettings
from gm_workspace.models import StoryIdea
from npcs.models import NPC

from .consumers import broadcast_combat_event
from .models import CombatLog, Encounter, Participant


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _next_sequence(encounter):
    """Return the next monotonic sequence number for an encounter's log.

    ``CombatLog`` enforces a unique ``(encounter, sequence)`` constraint,
    so callers must always allocate via this helper to avoid IntegrityError.
    """
    current = encounter.log_entries.aggregate(Max("sequence"))["sequence__max"] or 0
    return current + 1


def _log(encounter, action_type, message, **data):
    """Append a single CombatLog row and fan-out a real-time broadcast.

    Keyword arguments are stuffed into the ``data`` JSONField so callers
    can attach arbitrary structured payloads (e.g. a participant id or
    a faction tag) without touching the schema.

    v0.15.6: after the row is committed, fire a Channels group broadcast
    on ``combat_<encounter_id>`` so any browser subscribed to the
    encounter's WebSocket sees the mutation in real time. The broadcast
    is wrapped in a defensive ``try/except`` — the consumer helper
    already swallows Redis-level exceptions, but the import / channel
    layer lookup itself could fail in non-ASGI contexts (e.g. running
    ``manage.py shell`` or migrations). A broadcast hiccup must NEVER
    500 a REST mutation.
    """
    entry = CombatLog.objects.create(
        encounter=encounter,
        sequence=_next_sequence(encounter),
        round_number=encounter.round_number,
        action_type=action_type,
        message=message,
        data=data,
    )
    # ---- Real-time fan-out (v0.15.6) -------------------------------------
    try:
        broadcast_combat_event(
            encounter.id,
            action_type,
            {
                "encounter_id": encounter.id,
                "sequence": entry.sequence,
                "round_number": encounter.round_number,
                "action_type": action_type,
                "message": message,
                "data": data,
                "timestamp": entry.created_at.isoformat(),
            },
        )
    except Exception:
        # Defence-in-depth: keep REST 200/302 even when the channel
        # layer is unavailable. The UI will degrade to manual refresh.
        pass
    return entry


def _safe_int(value, fallback=0):
    """Cast a catalogue field to int, falling back gracefully.

    The combat NPC catalogue stores everything as strings (the editor
    is row-based and free-text), so spawn-time int casts must be
    defensive.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _roll_d10():
    """Single d10 face for WoD 2.0 initiative tiebreak.

    Uses ``secrets.randbelow`` for cryptographic-quality randomness —
    same source as the rest of the project's roll endpoints. Returns
    an int in ``[1, 10]``.
    """
    return secrets.randbelow(10) + 1


def _clamp_again_local(value):
    """Clamp a weapon ``again`` value to one of {8, 9, 10}.

    v0.15.19 — deliberate local copy of ``exodus.models._clamp_again``.
    The cross-app import would force the combat module to drag the
    site-settings model graph in at module-load time, which has caused
    cold-start cycles before. This helper has a five-line body and the
    semantics are stable; the cost of the duplication is negligible
    versus the import-graph footprint. Bad / out-of-range / None input
    silently collapses to 10 (classic 10-again).
    """
    try:
        v = int(value)
    except (TypeError, ValueError):
        return 10
    if v in (8, 9, 10):
        return v
    return 10


def _roll_pool(n, again_threshold=10):
    """Roll ``n`` d10s and count WoD 2.0 successes with X-again explode.

    The success threshold is always ``8+`` — a rolled face of 8, 9, or
    10 is one success. The ``again_threshold`` controls only the
    EXPLOSION trigger, i.e. which faces re-roll:

      * 10 (default, classic 10-again): re-roll on 10.
      * 9 (9-again): re-roll on 9 or 10.
      * 8 (8-again): re-roll on 8, 9, or 10.

    v0.15.19 — the threshold becomes weapon-specific. ``again_threshold``
    is read from the equipped weapon's snapshot
    (``weapon_data["again"]``) by ``_resolve_single_attack``; non-attack
    pool rolls (e.g. dodge) leave it at the 10 default. Bad / out-of-
    range input is clamped to ``[8, 10]`` defensively in case a tampered
    value reaches us.

    Returns ``(successes, dice)`` where ``dice`` is a list of dicts::

        [{"face": int, "kind": "base"|"explode",
          "from_index": int|None, "success": bool,
          "exploded": bool}, ...]

    'base' dice are the initial pool. 'explode' dice are re-rolls
    triggered by a face that hit the explosion threshold.
    ``from_index`` on an explode die points to the PARENT die's
    position in the list. ``success`` is True iff ``face >= 8``.
    ``exploded`` (NEW in v0.15.19) is True iff this die's face hit the
    explosion threshold AND triggered a re-roll — used by the renderer
    to visually distinguish trigger-faces from non-trigger successes
    when the threshold is 9 or 8 (a 9 in 9-again should glow like a
    classic 10; a 9 in 10-again should not).

    Explosion recursion is capped at 5 levels per starting die so a
    pathological all-trigger streak can't loop indefinitely.
    """
    if n <= 0:
        return 0, []
    # Defensive clamp — the caller normally goes through
    # ``_clamp_again_local`` already, but a stray ``None`` or arbitrary
    # int from a hand-rolled call still has to land safely.
    threshold = max(8, min(10, int(again_threshold or 10)))
    dice = []
    successes = 0
    for _ in range(n):
        base_idx = len(dice)
        face = _roll_d10()
        is_succ = face >= 8
        triggers = face >= threshold
        dice.append({
            "face": face,
            "kind": "base",
            "from_index": None,
            "success": is_succ,
            "exploded": triggers,
        })
        if is_succ:
            successes += 1
        # X-again: keep rolling while the latest face hits the
        # threshold, capped at 5 levels of recursion. ``from_index``
        # chains each explode back to its immediate parent (which may
        # itself be an explode die).
        parent_idx = base_idx
        parent_face = face
        depth = 0
        while parent_face >= threshold and depth < 5:
            explode_face = _roll_d10()
            explode_succ = explode_face >= 8
            explode_triggers = explode_face >= threshold
            dice.append({
                "face": explode_face,
                "kind": "explode",
                "from_index": parent_idx,
                "success": explode_succ,
                "exploded": explode_triggers,
            })
            if explode_succ:
                successes += 1
            parent_idx = len(dice) - 1
            parent_face = explode_face
            depth += 1
    return successes, dice


def _normalize_dice_payload(dice_raw):
    """Coerce a CombatLog ``data["dice"]`` payload to the structured shape.

    Accepts:

      * v0.15.17 and earlier — flat list of ints, e.g. ``[10, 7, 8]``.
        Every entry is marked ``kind="base"`` because the explosion
        chain was not recorded at the time. ``exploded`` back-fills
        conservatively to ``face == 10`` because every legacy attack
        was 10-again — non-10 trigger faces couldn't have existed.
        The renderer cannot show a parent → re-roll arrow on legacy
        rows; this is by design.

      * v0.15.18 — list of dicts in the structured shape but missing
        the ``exploded`` flag introduced in v0.15.19. Same conservative
        back-fill (``face == 10``) — those attacks were all 10-again
        because the threshold wasn't yet recorded.

      * v0.15.19+ — list of dicts including the ``exploded`` flag,
        which the resolver now writes accurately based on the
        weapon's recorded ``again`` threshold. A 9-again 9 lights up
        as a trigger; a 10-again 9 does not.

    Always returns a list — empty on garbage input or ``None``.
    """
    if not isinstance(dice_raw, list):
        return []
    out = []
    for d in dice_raw:
        if isinstance(d, int):
            # v0.15.17 and earlier — every legacy roll was 10-again,
            # so a 10 is the only face that could have triggered.
            out.append({
                "face": d,
                "kind": "base",
                "from_index": None,
                "success": d >= 8,
                "exploded": d == 10,
            })
        elif isinstance(d, dict) and "face" in d:
            face = int(d.get("face", 0))
            out.append({
                "face": face,
                "kind": d.get("kind", "base"),
                "from_index": d.get("from_index"),
                "success": bool(d.get("success", face >= 8)),
                # v0.15.19 — back-compat default for v0.15.18 rows that
                # pre-date the flag. ``face == 10`` is the only
                # conservative back-fill (those attacks were 10-again).
                "exploded": bool(d.get("exploded", face == 10)),
            })
    return out


# ---------------------------------------------------------------------------
# v0.15.5 — wound penalties, conditions, damage upgrades
# ---------------------------------------------------------------------------


# Hardcoded condition vocabulary. ``atk_mod`` and ``def_mod`` are
# applied additively in ``_condition_attack_modifier`` and
# ``_condition_defense_modifier``; sentinels (``-99`` / ``99``) are
# clamped by the special-case branches in ``_compute_defense`` so
# arithmetic stays safe. ``note`` is reserved for future tooltip
# surfacing on the row template.
CONDITION_DEFS = {
    "prone": {
        "label": "PRONE",
        "atk_mod": 0,
        "def_mod": -2,
        "note": "Easier to hit in melee, harder to be hit at range "
                "(GM judgment for ranged bonus).",
    },
    "stunned": {
        "label": "STUNNED",
        "atk_mod": -2,
        "def_mod": -2,
        "note": "Loses next turn (GM enforces on Next Turn).",
    },
    "blinded": {
        "label": "BLINDED",
        "atk_mod": -3,
        "def_mod": -2,
        "note": "Sees nothing — at range, attacks miss automatically "
                "(GM call).",
    },
    "grappled": {
        "label": "GRAPPLED",
        "atk_mod": -2,
        "def_mod": -2,
        "note": "Cannot move; reduced pools.",
    },
    "incapacitated": {
        "label": "INCAPACITATED",
        "atk_mod": -99,
        "def_mod": -99,
        "note": "Out. Cannot act, cannot defend.",
    },
    "defense_full": {
        "label": "FULL DEFENSE",
        "atk_mod": 0,
        "def_mod": 99,
        "note": "Defense doubled this round (clears at next turn).",
    },
    "dodging": {
        "label": "DODGING",
        "atk_mod": 0,
        "def_mod": 99,
        "note": "Rolled dodge pool replaces normal defense (clears "
                "at next turn).",
    },
}

# Stance tags are managed by the FULL DEFENSE / DODGE buttons rather
# than the generic ADD CONDITION dropdown — they require a dice roll
# (dodge) or auto-double math (full defense) so they cannot be set
# via raw text submission.
_STANCE_TAGS = {"defense_full", "dodging", "dodge_pending"}


def _wound_penalty(participant):
    """WoD 2.0 wound penalty based on the rightmost filled health box.

    The 3 rightmost boxes carry -1 / -2 / -3 penalties left → right.
    Returns a non-positive int (``0`` = no penalty). Used by the
    attack pool composition and surfaced as a small chip on the row.
    """
    total = (
        participant.health_bashing
        + participant.health_lethal
        + participant.health_aggravated
    )
    hm = participant.health_max
    if total >= hm:
        return -3   # rightmost box filled (incapacitated)
    if total == hm - 1:
        return -2
    if total == hm - 2:
        return -1
    return 0


def _has_condition(participant, tag):
    """Return True if a flat condition tag is set on the participant."""
    return tag in (participant.conditions or [])


def _has_prefix_condition(participant, prefix):
    """Return True if any tag starts with ``prefix:`` (e.g. ``dodging:3``)."""
    return any(c.startswith(prefix + ":") for c in (participant.conditions or []))


def _strip_prefix_conditions(conditions, prefix):
    """Filter a conditions list, removing any ``prefix:N`` entries."""
    return [c for c in (conditions or []) if not c.startswith(prefix + ":")]


def _dodge_successes(participant):
    """Read the stored dodge pool from a ``dodging:N`` tag, or 0."""
    for c in (participant.conditions or []):
        if c.startswith("dodging:"):
            try:
                return int(c.split(":", 1)[1])
            except (ValueError, IndexError):
                return 0
    return 0


# ---------------------------------------------------------------------------
# v0.15.14 — AIM, burst fire, autofire spread
# ---------------------------------------------------------------------------
#
# AIM is a full-turn action that grants +1 cumulative dice on the next
# attack against a specified target, stackable up to +3 over consecutive
# aim turns. State lives in the participant's conditions list as a tag
# of shape ``aiming_at:<target_id>:<turns>`` — no schema change needed.
# Burst fire piggy-backs on the attack form (single / short / medium /
# long) and adds +0/+1/+2/+3 dice. Autofire spread (medium/long only)
# resolves separate attack rolls against extra targets at -1 cumulative
# per spread index.

# Burst-mode dice bonus table. Single fire is the default and the only
# option for non-auto-capable weapons. Short burst is a 3-round burst
# (+1), medium is a ~10-round burst (+2), long is full-auto (+3).
BURST_BONUSES = {"single": 0, "short": 1, "medium": 2, "long": 3}

# Per burst mode caps on the number of EXTRA targets engaged via spread.
# Single / short bursts cannot spread (spread is autofire-only). Medium
# burst engages up to 2 extras (3 targets total); long burst up to 5
# extras (6 targets total — ample for any realistic skirmish, and the
# cumulative -1 per index makes any further extras essentially zero
# pool anyway).
BURST_MAX_EXTRAS = {"single": 0, "short": 0, "medium": 2, "long": 5}


def _weapon_is_auto_capable(weapon_data):
    """True iff the equipped weapon's catalogue entry has
    ``auto_capable: True``. Empty / missing weapon → False.

    Used by the attack form to gate the FIRE MODE selector and by the
    server-side resolver to fall back to single-fire on tampered POSTs
    that try to spend burst dice without the supporting weapon.
    """
    if not weapon_data:
        return False
    return bool(weapon_data.get("auto_capable", False))


def _parse_aim_tag(condition_tag):
    """Parse 'aiming_at:42:2' → (target_id=42, turns=2). Returns None
    on malformed input.

    Defensive against any non-string / non-aim-prefix value so the
    caller can iterate over the full conditions list and pull the
    aim state without pre-filtering.
    """
    if not isinstance(condition_tag, str):
        return None
    if not condition_tag.startswith("aiming_at:"):
        return None
    parts = condition_tag.split(":")
    if len(parts) != 3:
        return None
    try:
        return int(parts[1]), int(parts[2])
    except ValueError:
        return None


def _aim_state(participant):
    """Return ``(target_id, turns)`` for the participant's current aim,
    or ``None`` if no aim tag is set.

    Only the first matching tag is returned — by construction the aim
    helpers strip any old tag before appending a new one, so at most
    one aim tag should ever be present on a participant.
    """
    for c in (participant.conditions or []):
        parsed = _parse_aim_tag(c)
        if parsed:
            return parsed
    return None


def _strip_aim(participant):
    """Remove any ``aiming_at:*`` tag from ``participant.conditions``
    in-place. Caller is responsible for ``participant.save(...)``.

    No-op when no aim tag is present. Used by every action that
    should break aim — taking damage, defending, dodging, attacking
    a different target, and the round-boundary clear in next_turn.
    """
    participant.conditions = [
        c for c in (participant.conditions or [])
        if not (isinstance(c, str) and c.startswith("aiming_at:"))
    ]


# ---------------------------------------------------------------------------
# v0.15.15 — Ammo tracking
# ---------------------------------------------------------------------------
#
# Magazines are tracked via an ``ammo:<N>`` condition tag on the
# participant — N is the current rounds-in-magazine count. Players have
# unlimited magazines (no reserve tracking); reload always resets the
# count to the catalogue's ``magazine`` value. This pattern mirrors
# ``dodging:N`` and ``aiming_at:tid:turns`` — no schema change required.
#
# Only Character / NPC participants with a snapshotted firearm
# weapon_data (category=="firearm") and a non-zero magazine size carry
# an ammo tag. Mooks remain ammo-free in v0.15.15 (their weapon is a
# free-text catalogue label, not a snapshot dict). Non-firearm weapons
# silently skip the ammo system.


def _parse_ammo_tag(condition_tag):
    """Parse ``'ammo:7'`` into the integer ``7``.

    Returns ``None`` for any non-string, non-prefix, or non-numeric
    value — defensive against legacy / hand-edited conditions lists so
    a malformed tag never crashes the row render.
    """
    if not isinstance(condition_tag, str):
        return None
    if not condition_tag.startswith("ammo:"):
        return None
    try:
        return int(condition_tag.split(":", 1)[1])
    except (ValueError, IndexError):
        return None


def _ammo_state(participant):
    """Return the current rounds-in-magazine for the participant.

    Iterates the conditions list and returns the first ``ammo:N`` tag's
    integer payload. Returns ``None`` if no ammo tag is present (which
    the caller reads as "no ammo state on file" — typically means the
    participant either has a non-firearm equipped, has nothing equipped,
    or is a mook).
    """
    for c in (participant.conditions or []):
        parsed = _parse_ammo_tag(c)
        if parsed is not None:
            return parsed
    return None


def _set_ammo(participant, rounds):
    """Strip any prior ``ammo:*`` tag, then append a fresh
    ``ammo:<rounds>`` tag in-place on ``participant.conditions``.

    Caller is responsible for ``participant.save(update_fields=
    ['conditions'])`` (or wider field set when called from another
    action). Idempotent — calling twice with the same value yields
    the same end state.
    """
    participant.conditions = [
        c for c in (participant.conditions or [])
        if not (isinstance(c, str) and c.startswith("ammo:"))
    ]
    participant.conditions.append(f"ammo:{int(rounds)}")


def _strip_ammo(participant):
    """Remove any ``ammo:*`` tag from ``participant.conditions``
    in-place. Caller is responsible for ``participant.save(...)``.

    Used when transitioning a participant *out* of an ammo-tracked
    state — typically when unequipping a firearm or equipping a
    non-firearm weapon (the previous mag count is no longer
    meaningful).
    """
    participant.conditions = [
        c for c in (participant.conditions or [])
        if not (isinstance(c, str) and c.startswith("ammo:"))
    ]


# ---------------------------------------------------------------------------
# v0.15.16 — off-hand ammo helpers (dual-wielding)
# ---------------------------------------------------------------------------
#
# Off-hand ammo lives on a parallel ``offhand_ammo:N`` condition tag,
# mirroring the main-hand ``ammo:N`` shape one-for-one. Two distinct
# tags rather than a single shared one because main-hand and off-hand
# magazines decrement independently — DUAL ATTACK fires one round of
# main-hand and one round of off-hand from a single trigger pull.
#
# v0.15.16 does NOT implement an off-hand reload action — when an
# off-hand firearm runs dry it stays empty until re-equipped (which
# refills via ``equip_offhand``). v0.15.17+ may add a dedicated
# off-hand reload.


def _parse_offhand_ammo_tag(tag):
    """Parse ``'offhand_ammo:7'`` into the integer ``7``.

    Returns ``None`` for any non-string, non-prefix, or non-numeric
    value — defensive against legacy / hand-edited conditions lists so
    a malformed tag never crashes the row render. Mirrors the shape of
    ``_parse_ammo_tag`` for the main hand.
    """
    if not isinstance(tag, str):
        return None
    if not tag.startswith("offhand_ammo:"):
        return None
    try:
        return int(tag.split(":", 1)[1])
    except (ValueError, IndexError):
        return None


def _offhand_ammo_state(participant):
    """Return current rounds-in-magazine for the participant's off-hand.

    Iterates the conditions list and returns the first
    ``offhand_ammo:N`` tag's integer payload. Returns ``None`` when no
    off-hand ammo tag is set (no off-hand equipped, off-hand is a
    non-firearm, or this is a mook).
    """
    for c in (participant.conditions or []):
        parsed = _parse_offhand_ammo_tag(c)
        if parsed is not None:
            return parsed
    return None


def _set_offhand_ammo(participant, rounds):
    """Strip any prior ``offhand_ammo:*`` tag, then append a fresh
    ``offhand_ammo:<rounds>`` tag in-place on
    ``participant.conditions``.

    Caller is responsible for ``participant.save(update_fields=
    ['conditions'])``. Idempotent — calling twice with the same value
    yields the same end state.
    """
    participant.conditions = [
        c for c in (participant.conditions or [])
        if not (isinstance(c, str) and c.startswith("offhand_ammo:"))
    ]
    participant.conditions.append(f"offhand_ammo:{int(rounds)}")


def _strip_offhand_ammo(participant):
    """Remove any ``offhand_ammo:*`` tag in-place. Caller saves.

    Used when un-equipping the off-hand or swapping in a non-firearm
    off-hand (the previous mag count is no longer meaningful).
    """
    participant.conditions = [
        c for c in (participant.conditions or [])
        if not (isinstance(c, str) and c.startswith("offhand_ammo:"))
    ]


def _has_ambidextrous_merit(actor):
    """Return True if the actor's underlying Character or NPC has the
    Ambidextrous merit attached.

    Mooks have no character / NPC sheet → always False. Two storage
    layers are checked, in priority order:

    1. **Canonical M2M** — ``source.merit_entries`` is a
       ``ManyToManyField`` to ``exodus.MeritDefinition`` (through
       ``CharacterMerit`` / ``NpcMerit``). A case-insensitive name
       match is the right shape: filtering on the M2M manager filters
       ``MeritDefinition`` rows directly (``name__iexact=...``), and
       the ORM JOINs through the through-table for us.
    2. **Legacy JSONField** — ``merits_old`` on both Character and
       NPC. Pre-M2M-migration sheets stored merits as a free-text
       JSON list (each entry either a dict with ``name`` key or a
       bare string). Checked second so a manually re-attached merit
       on the canonical layer wins over a stale JSON entry.

    A False result here means the off-hand attack pays the -2 dice
    penalty. A typo would silently make players lose dice they
    earned, so the M2M path is verified by a Django-shell check at
    development time (see the v0.15.16 release notes for the exact
    assertion).
    """
    if actor.participant_kind == "mook":
        return False
    source = actor.character or actor.npc
    if source is None:
        return False
    # Canonical: M2M filter against MeritDefinition.name. The M2M
    # field's related_model is MeritDefinition (verified at dev time),
    # so .filter(name__iexact=...) hits the catalogue's name column.
    try:
        if source.merit_entries.filter(name__iexact="Ambidextrous").exists():
            return True
    except Exception:
        # Defensive: if the M2M manager somehow raises (mock instance,
        # unsaved object, partial migration state), fall through to
        # the legacy JSON layer rather than 500-ing the attack form.
        pass
    # Legacy JSON list: free-text entries with optional 'name' key.
    legacy = getattr(source, "merits_old", None) or []
    for entry in legacy:
        if isinstance(entry, dict):
            n = entry.get("name", "")
        elif isinstance(entry, str):
            n = entry
        else:
            n = ""
        if isinstance(n, str) and n.strip().lower() == "ambidextrous":
            return True
    return False


# v0.15.15 — rounds-fired-per-burst-mode lookup. Mirrors the
# ``BURST_BONUSES`` dice-bonus table but in the inverse direction
# (cost rather than benefit). Keep these two tables aligned: any
# new burst mode must be added to both.
BURST_AMMO_COST = {"single": 1, "short": 3, "medium": 10, "long": 20}


# ---------------------------------------------------------------------------
# v0.15.17 — Gun Fu merit integration
# ---------------------------------------------------------------------------
#
# The Gun Fu merit (soldier-only, 1-5 dots) grants "1 free success per
# dot per session in gun combat". The character sheet already exposes
# spend/reset UI (characters/views.py:225-244) and the JSONField
# ``Character.merit_uses`` tracks per-session usage. v0.15.17 wires
# the merit into the combat resolver so soldiers paying for the dots
# actually receive the bonus successes during firearm encounters.
#
# State helper returns a (rating, used, remaining) triple. Distribution
# helper splits a player-declared total spend across all attack targets
# in a single action (primary + spread extras + off-hand on dual-wield).


def _gun_fu_state(actor):
    """Return (rating, used, remaining) for the actor's Gun Fu merit.

    Returns ``(0, 0, 0)`` for any actor that cannot benefit from Gun Fu:

    * Mooks (no character FK).
    * NPCs (the NPC sheet has no per-session merit-use tracking yet —
      the spend / reset UI lives only on Character sheets, so emitting
      a Gun Fu input on an NPC row would be a one-way street that
      drains uses with no way to refresh them).
    * Characters without the Gun Fu merit attached.
    * Characters whose ``character_class`` is not ``soldier`` (defense
      in depth — the merit is canonically soldier-locked at the
      catalogue level, but a hand-edited DB row could attach it
      elsewhere; we silently ignore that).

    Soldiers with Gun Fu and remaining session uses return positive
    ``remaining``. Reads ``CharacterMerit.rating`` (the through-table
    field, related_name ``character_merits`` per
    ``characters.models.CharacterMerit.Meta``) as the dot total and
    ``Character.merit_uses["Gun Fu"]`` as the count consumed this
    session.
    """
    if actor.participant_kind != "character" or actor.character is None:
        return 0, 0, 0
    char = actor.character
    if (char.character_class or "").strip().lower() != "soldier":
        return 0, 0, 0
    # Resolve through the canonical M2M through-table. ``character_merits``
    # is the related_name on CharacterMerit (characters/models.py:155-157).
    # Case-insensitive name match shields against catalogue casing drift.
    cm = char.character_merits.filter(merit__name__iexact="Gun Fu").first()
    if cm is None:
        return 0, 0, 0
    rating = int(cm.rating or 0)
    used = int((char.merit_uses or {}).get("Gun Fu", 0))
    remaining = max(0, rating - used)
    return rating, used, remaining


def _distribute_gun_fu(total_uses, num_targets):
    """Spread ``total_uses`` Gun Fu auto-successes across ``num_targets``.

    Distribution is as even as possible. The integer remainder lands on
    the **first** targets in declaration order so the primary target
    gets the bonus when the math doesn't divide cleanly. Order of
    targets in the caller is fixed: primary main-hand → spread extras
    in their normal order → off-hand last (per the v0.15.17 spec).

    Examples (matching the spec)::

        _distribute_gun_fu(5, 4) == [2, 1, 1, 1]
        _distribute_gun_fu(5, 2) == [3, 2]
        _distribute_gun_fu(3, 1) == [3]
        _distribute_gun_fu(0, 4) == [0, 0, 0, 0]
        _distribute_gun_fu(7, 4) == [2, 2, 2, 1]

    Empty / zero edge cases collapse to ``[]`` or ``[0, ...]`` so the
    caller can always index by target slot.
    """
    if num_targets <= 0:
        return []
    if total_uses <= 0:
        return [0] * num_targets
    base = total_uses // num_targets
    extra = total_uses % num_targets
    return [base + (1 if i < extra else 0) for i in range(num_targets)]


def _condition_attack_modifier(participant):
    """Sum ``atk_mod`` across active conditions, floored at -10.

    Sentinel ``-99`` from ``incapacitated`` is allowed to dominate —
    the floor still leaves the attacker pool effectively zero after
    the ``max(0, ...)`` clamp in the resolver.
    """
    mods = sum(
        CONDITION_DEFS.get(c, {}).get("atk_mod", 0)
        for c in (participant.conditions or [])
    )
    return max(-10, mods)


def _condition_defense_modifier(participant):
    """Sum ``def_mod`` across active conditions, floored at -10.

    Sentinels (``-99`` for incapacitated, ``99`` for stances) are
    NOT applied through this helper — ``_compute_defense`` short-
    circuits those special cases before delegating here. This helper
    only contributes the ordinary -2/-3 condition modifiers.
    """
    mods = 0
    for c in (participant.conditions or []):
        # Skip stance tags entirely — they're handled in
        # _compute_defense's special-case branches.
        if c in _STANCE_TAGS:
            continue
        if c.startswith("dodging:"):
            continue
        mods += CONDITION_DEFS.get(c, {}).get("def_mod", 0)
    return max(-10, mods)


def _baseline_defense(participant):
    """Compute the unmodified defense pool (no conditions, no stances).

    Mirror of the v0.15.4 ``_compute_defense`` body, factored out so
    ``_compute_defense`` can apply stance multipliers / replacements
    cleanly.
    """
    if participant.defense_override is not None:
        return participant.defense_override
    if participant.participant_kind == "mook":
        return participant.mook_defense or 0
    source = participant.character or participant.npc
    if source is None:
        return 0
    try:
        dex = int(source.attributes["finesse"]["physical"])
        wits = int(source.attributes["finesse"]["mental"])
        athletics = int(source.skills["physical"].get("Athletics", 0))
        return min(dex, wits) + athletics
    except (KeyError, TypeError, ValueError):
        return 0


def _compute_defense(participant):
    """Compute a target's defense pool including conditions / stances.

    Special cases honour the v0.15.5 condition vocabulary:

    * ``incapacitated`` → 0 (target cannot defend at all).
    * ``dodging:N``     → N (the rolled dodge successes replace the
                          normal defense pool entirely).
    * ``defense_full``  → baseline doubled, then ordinary condition
                          modifiers applied on top.

    Falls back to the v0.15.4 baseline (``min(Dex, Wits) +
    Athletics`` for character / NPC, ``mook_defense`` for mooks,
    overridden by ``defense_override`` if pinned) plus the sum of
    plain condition modifiers (``prone``, ``stunned``, etc.).
    """
    if _has_condition(participant, "incapacitated"):
        return 0
    if _has_prefix_condition(participant, "dodging"):
        return _dodge_successes(participant)
    baseline = _baseline_defense(participant)
    if _has_condition(participant, "defense_full"):
        baseline *= 2
    return max(0, baseline + _condition_defense_modifier(participant))


def _apply_damage(participant, amount, dtype):
    """Apply WoD 2.0 damage with track upgrade semantics.

    Damage type ladder: B (lowest) → L → A (highest). Empty boxes
    fill normally up to ``health_max``. Once full, overflow displaces
    lower-severity damage upward:

      * incoming **B** → fills empty boxes; overflow is dropped
        (B can't displace anything).
      * incoming **L** → fills empty boxes; overflow upgrades B → L
        (one B box becomes one L box per overflow point).
      * incoming **A** → fills empty boxes; overflow upgrades B → A,
        then L → A (one box per overflow point each).

    Returns ``(applied, upgraded, overflow)`` for log payload
    purposes:

    * ``applied``  — boxes filled into previously empty slots.
    * ``upgraded`` — boxes upgraded from a lower track to this one.
    * ``overflow`` — points that fell off the right edge entirely
      (e.g. a B incoming on a full track, or an L incoming on a
      track full of L+).
    """
    b = participant.health_bashing
    l = participant.health_lethal
    a = participant.health_aggravated
    hm = participant.health_max
    free = max(0, hm - (b + l + a))

    applied = min(free, amount)
    overflow = amount - applied
    upgrades = 0

    if dtype == "B":
        b += applied
        # Bashing can't displace anything — overflow is dropped.
    elif dtype == "L":
        l += applied
        # Lethal overflow upgrades a single bashing box per point.
        while overflow > 0 and b > 0:
            b -= 1
            l += 1
            overflow -= 1
            upgrades += 1
    elif dtype == "A":
        a += applied
        # Aggravated overflow upgrades B then L per point.
        while overflow > 0 and b > 0:
            b -= 1
            a += 1
            overflow -= 1
            upgrades += 1
        while overflow > 0 and l > 0:
            l -= 1
            a += 1
            overflow -= 1
            upgrades += 1

    participant.health_bashing = b
    participant.health_lethal = l
    participant.health_aggravated = a
    # v0.15.14 — taking damage breaks aim. We strip any aiming_at:*
    # tag here and add ``conditions`` to the update_fields list when
    # the strip actually changed something. Done inline so every
    # caller of _apply_damage benefits without separate plumbing.
    update_fields = ["health_bashing", "health_lethal", "health_aggravated"]
    if applied + upgrades + overflow > 0 and _aim_state(participant) is not None:
        _strip_aim(participant)
        update_fields.append("conditions")
    participant.save(update_fields=update_fields)
    return applied, upgrades, overflow


def _specialisations_for_skill(actor, skill_name):
    """Return list of specialisation names that match the given skill on
    the actor's underlying Character or NPC.

    Returns ``[]`` for mooks (no character/npc FK), unknown actors, or
    when the actor has no matching specialisations. Skill name match
    is case-insensitive.

    Specialisations are stored as a JSONField list of dicts with
    ``'skill'`` and ``'name'`` keys (see ``Character.specialisations``
    and ``NPC.specialisations``). Malformed rows (missing keys,
    non-string values) are silently filtered so a hand-edited record
    never raises here.
    """
    if actor.participant_kind == "mook" or not skill_name:
        return []
    source = actor.character or actor.npc
    if source is None:
        return []
    raw = getattr(source, "specialisations", None) or []
    needle = skill_name.strip().lower()
    out = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        s = entry.get("skill", "")
        n = entry.get("name", "")
        if not isinstance(s, str) or not isinstance(n, str):
            continue
        if s.strip().lower() == needle and n.strip():
            out.append(n.strip())
    return out


def _actor_total_pool(actor, weapon_data, gm_modifier, weapon_skill_name="",
                     spend_willpower=False, applied_specialisations=None):
    """Compose the attacker's full pre-cover, pre-defense dice pool.

    Wraps ``_attack_dice_pool`` (the catalogue + skill base) and adds
    the v0.15.5 modifiers:

    * Wound penalty   — non-positive int from ``_wound_penalty``.
    * Condition mods  — sum of ``atk_mod`` across active conditions.
    * Willpower spend — ``+3`` flat when ``spend_willpower=True``
      (caller is responsible for actually decrementing
      ``willpower_current`` if the spend goes through).
    * Specialisations (v0.15.10) — ``+1`` per validated specialisation
      name in ``applied_specialisations``. The caller is responsible
      for validating each entry against
      ``_specialisations_for_skill(actor, weapon_skill_name)`` before
      passing it through; this helper trusts what it gets.
    """
    base = _attack_dice_pool(actor, weapon_data, gm_modifier, weapon_skill_name)
    base += _wound_penalty(actor)
    base += _condition_attack_modifier(actor)
    if spend_willpower:
        base += 3
    if applied_specialisations:
        # Each validated specialisation grants +1 die. The caller has
        # already filtered out unknown / non-matching names, so we
        # simply count.
        base += len(applied_specialisations)
    return base


# ---------------------------------------------------------------------------
# v0.15.9 — weapon-skill auto-pick + numeric attack-pool preview
# ---------------------------------------------------------------------------

# Map of weapon catalogue ``category`` → WoD 2.0 skill name. Anything
# not listed (or a participant with no equipped weapon) falls back to
# Brawl, since unarmed strikes use Brawl in WoD 2.0. The mapping is
# intentionally small — extend here when new categories land in the
# weapon catalogue, not in the calling sites.
WEAPON_CATEGORY_SKILL = {
    "firearm":     "Firearms",
    "thrown":      "Athletics",
    "melee":       "Weaponry",
    "improvised":  "Weaponry",
}


def _weapon_skill_for(weapon_data):
    """Map weapon catalogue 'category' to WoD 2.0 skill name.

    Returns ``"Brawl"`` when there's no equipped weapon (unarmed).
    Unknown / missing category strings fall back to ``"Weaponry"``
    so a malformed catalogue row still resolves to *something*
    sensible rather than zero pool.
    """
    if not weapon_data:
        return "Brawl"
    category = (weapon_data or {}).get("category", "")
    return WEAPON_CATEGORY_SKILL.get(category, "Weaponry")


def _attack_preview(actor, weapon_data, gm_modifier, weapon_skill_name=""):
    """Return a dict breaking down the attacker's pool for UI preview.

    Pure server-side computation. Mirrors the same arithmetic as
    ``_attack_dice_pool`` + ``_actor_total_pool``, but split into the
    component fields the row template renders so the player sees
    *where* their dice come from before pulling the trigger.

    Note: defense and cover penalty are NOT subtracted — those are
    target-dependent and resolved at attack time. Same for willpower
    (the +3 is decided by a checkbox at submit time, not a preview
    field). The preview is therefore the actor's pre-target pool
    ceiling against an unmodified target with no cover and no WP.

    Auto-picks the skill via ``_weapon_skill_for(weapon_data)`` when
    ``weapon_skill_name`` is empty (or whitespace) — the same
    fallback the resolver applies in the attack view.
    """
    # Resolve the skill once. Empty / whitespace → auto-pick.
    skill_name = (weapon_skill_name or "").strip()
    if not skill_name:
        skill_name = _weapon_skill_for(weapon_data)

    base = 0
    skill_value = 0
    if actor.participant_kind == "mook":
        # Mooks have no skill axis — the catalogue's combat_pool is
        # already the entire offensive pool, so we surface it under
        # ``base`` and leave skill at zero.
        base = (actor.mook_combat_pool or 0)
    else:
        source = actor.character or actor.npc
        if source is not None:
            try:
                base = int(source.attributes["finesse"]["physical"])
            except (KeyError, TypeError, ValueError):
                base = 0
            # Mirror the resolver's tier-cascade: physical first, then
            # mental, then social — first non-zero wins. Defensive
            # against partial sheets so a missing tier never raises.
            for tier in ("physical", "mental", "social"):
                try:
                    val = int(source.skills[tier].get(skill_name, 0))
                    if val:
                        skill_value = val
                        break
                except (KeyError, TypeError, ValueError):
                    continue

    weapon_dice = _safe_int((weapon_data or {}).get("dice_modifier"), 0)
    wound_pen = _wound_penalty(actor)
    cond_mod = _condition_attack_modifier(actor)
    gm_mod = _safe_int(gm_modifier, 0)

    total = max(
        0,
        base + skill_value + weapon_dice + wound_pen + cond_mod + gm_mod,
    )

    # v0.15.10 — surface the actor's specialisations relevant to the
    # resolved skill so the row template can render checkboxes. The
    # preview's ``total`` is the *base* pool — JS adds +1 per ticked
    # box client-side, the server re-validates on submit.
    specialisations = _specialisations_for_skill(actor, skill_name)

    # v0.15.14 — burst-fire options. ``available`` is True only when
    # the equipped weapon is auto-capable (and even then the SINGLE
    # mode is always available). The template can render a select
    # with disabled non-available options, or omit them entirely.
    auto_capable = _weapon_is_auto_capable(weapon_data)
    burst_options = [
        {"value": "single", "label": "SINGLE",
         "bonus": 0, "available": True},
        {"value": "short", "label": "SHORT BURST (3rd, +1)",
         "bonus": 1, "available": auto_capable},
        {"value": "medium", "label": "MEDIUM BURST (10rd, +2)",
         "bonus": 2, "available": auto_capable},
        {"value": "long", "label": "LONG BURST / FULL AUTO (+3)",
         "bonus": 3, "available": auto_capable},
    ]

    return {
        "base":             base,
        "skill":            skill_value,
        "skill_name":       skill_name,
        "weapon_dice":      weapon_dice,
        "wound_penalty":    wound_pen,
        "condition_mod":    cond_mod,
        "gm_modifier":      gm_mod,
        "willpower_bonus":  0,   # preview only — WP is a submit-time toggle
        "specialisations":  specialisations,
        "spec_bonus":       0,   # preview is pre-tick; JS recomputes live
        # v0.15.14 — burst-fire options surfaced for the FIRE MODE
        # select. ``auto_capable`` mirrors the equipped weapon's flag
        # so the template can disable the select entirely (rather
        # than hiding it) when the weapon is single-shot only.
        "burst_options":    burst_options,
        "auto_capable":     auto_capable,
        "burst_bonus":      0,   # preview is single-fire; JS recomputes live
        "total":            total,
    }


# ---------------------------------------------------------------------------
# Defense + cover (v0.15.4, defense extended in v0.15.5)
# ---------------------------------------------------------------------------


def _cover_penalty(cover_state):
    """Map cover state to attacker pool penalty.

    Returns a non-negative integer to subtract from the attacker's
    pool (the math is one-sided so we don't double-count by also
    bumping defense). The sentinel string ``"BLOCKED"`` signals that
    the shot is impossible — full cover should write a
    ``blocked_by_cover`` log row and skip the roll entirely.
    """
    return {"none": 0, "light": 2, "heavy": 4, "full": "BLOCKED"}.get(
        cover_state, 0
    )


def _parse_armor_rating(rating_str):
    """Parse a ``"B/L"`` armor rating string into ``(B_armor, L_armor)``.

    Robust against the catalogue's free-text quirks — ``"—"``,
    ``"-"``, empty strings, malformed pairs all fall back to
    ``(0, 0)``. Whitespace inside the pair is stripped. Aggravated
    damage bypasses armor entirely so this helper is only consulted
    for B / L hits.
    """
    if not rating_str or rating_str.strip() in ("—", "-", ""):
        return 0, 0
    parts = rating_str.replace(" ", "").split("/")
    if len(parts) != 2:
        return 0, 0
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return 0, 0


def _parse_weapon_damage(damage_field):
    """Parse a weapon catalogue ``damage`` value into ``(amount, type)``.

    The catalogue stores damage as a free-text string like ``"2L"``,
    ``"1B"``, ``"4L close / 2L long"``, or even ``"5L (both barrels)"``.
    For v0.15.4 we only need the leading numeric magnitude and the
    first ``B``/``L``/``A`` suffix character — the GM modifier is the
    pressure-relief valve for everything more nuanced.

    Falls back to ``(0, "L")`` for missing / unparseable input —
    lethal is the WoD 2.0 default and zero damage is harmless.
    """
    if damage_field is None:
        return 0, "L"
    text = str(damage_field).strip()
    if not text:
        return 0, "L"
    # Read leading digits as the damage magnitude.
    digits = ""
    for ch in text:
        if ch.isdigit():
            digits += ch
        else:
            break
    amount = int(digits) if digits else 0
    # First B / L / A character anywhere in the string is the type.
    damage_type = "L"
    for ch in text:
        upper = ch.upper()
        if upper in ("B", "L", "A"):
            damage_type = upper
            break
    return amount, damage_type


def _attack_dice_pool(actor, weapon_data, gm_modifier, weapon_skill_name=""):
    """Compute the attacker's pre-cover, pre-defense dice pool.

    Mooks short-circuit on ``mook_combat_pool`` (the catalogue
    encodes their entire offensive pool already). Character / NPC
    starts at Dexterity, then adds the named skill's value if found
    (searching physical → mental → social so the GM can pick
    Firearms / Brawl / Weaponry without specifying the tier). The
    weapon's dice modifier (catalogue field, optional) and the GM's
    free-form signed integer modifier are applied last.
    """
    base = 0
    if actor.participant_kind == "mook":
        base = (actor.mook_combat_pool or 0)
    else:
        source = actor.character or actor.npc
        if source is not None:
            try:
                dex = int(source.attributes["finesse"]["physical"])
                base = dex
            except (KeyError, TypeError, ValueError):
                base = 0
            if weapon_skill_name:
                # Try physical first (Firearms / Weaponry / Brawl all
                # live there), then mental, then social — first
                # non-zero wins. Defensive against partial sheets.
                for tier in ("physical", "mental", "social"):
                    try:
                        skill_val = int(
                            source.skills[tier].get(weapon_skill_name, 0)
                        )
                        if skill_val:
                            base += skill_val
                            break
                    except (KeyError, TypeError, ValueError):
                        continue
    weapon_dice = _safe_int((weapon_data or {}).get("dice_modifier"), 0)
    return base + weapon_dice + gm_modifier


def _compute_initiative(participant):
    """Compute ``(modifier, d10, score)`` for a Participant.

    * Character / NPC: ``Dexterity (finesse.physical) + Composure
      (resistance.social) + 1d10``. Missing keys / non-int values fall
      back to modifier ``0`` so partial sheets never crash the roll.
    * Mook: ``combat_pool // 2 + 1d10``. ``None`` combat pool falls
      back to ``0``.

    The tuple shape is consistent across kinds so the caller can log a
    single uniform message.
    """
    if participant.participant_kind == "mook":
        modifier = (participant.mook_combat_pool or 0) // 2
    else:
        # Prefer character FK, fall back to npc FK; either may be
        # SET_NULL'd by a delete on the underlying actor.
        source = participant.character or participant.npc
        if source is None:
            modifier = 0
        else:
            try:
                dex = int(source.attributes["finesse"]["physical"])
                composure = int(source.attributes["resistance"]["social"])
                modifier = dex + composure
            except (KeyError, TypeError, ValueError):
                modifier = 0
    d10 = _roll_d10()
    return modifier, d10, modifier + d10


def _gm_only(view):
    """Decorator factory: 403 unless ``request.user.is_superuser``.

    Implemented inline rather than via ``user_passes_test`` so the
    response body matches the rest of the clearance-gate aesthetic.
    """

    def wrapped(request, *args, **kwargs):
        if not request.user.is_superuser:
            return HttpResponseForbidden("ACCESS DENIED.")
        return view(request, *args, **kwargs)

    wrapped.__name__ = view.__name__
    wrapped.__doc__ = view.__doc__
    return wrapped


def _can_control_participant(user, participant):
    """A user can control a Participant iff:
       * they are a superuser (GM), OR
       * the participant.character is owned by them.

    NPCs and mooks are always GM-only — players cannot drive them.
    """
    if user.is_superuser:
        return True
    if participant.character_id is None:
        return False
    return participant.character.owner_id == user.id


def _gm_or_owner(participant_arg="participant_id"):
    """Decorator factory: superuser passes; otherwise the user must
    own the Character on the Participant identified by URL kwarg
    ``participant_arg``. 403 otherwise.

    Use this on every action view that mutates a single participant
    where players are allowed to drive their own character.

    Note: this enforces the *ownership* gate (the hard 403). View
    bodies remain responsible for action-specific soft checks
    (active-turn, condition allow-lists, willpower direction) — those
    surface as flash-message redirects rather than 403s, so a player
    who fat-fingers an illegal action gets a meaningful explanation
    rather than the bare clearance-gate response.
    """

    def decorator(view):
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return HttpResponseForbidden("ACCESS DENIED.")
            if request.user.is_superuser:
                return view(request, *args, **kwargs)
            participant_id = kwargs.get(participant_arg)
            if participant_id is None:
                return HttpResponseForbidden("ACCESS DENIED.")
            try:
                p = Participant.objects.select_related("character").get(
                    pk=participant_id
                )
            except Participant.DoesNotExist:
                return HttpResponseForbidden("ACCESS DENIED.")
            if not _can_control_participant(request.user, p):
                return HttpResponseForbidden("ACCESS DENIED.")
            return view(request, *args, **kwargs)

        wrapped.__name__ = view.__name__
        wrapped.__doc__ = view.__doc__
        return wrapped

    return decorator


# ---------------------------------------------------------------------------
# Page views
# ---------------------------------------------------------------------------


@login_required
def encounter_list_page(request):
    """GET — render the encounter directory.

    v0.15.7 — accessible to any authenticated user. GMs (superuser)
    see every encounter; players see only encounters they have at
    least one Character participating in. The "+ NEW ENCOUNTER" form
    in the template is gated on superuser status, so the same view
    can serve both audiences without leaking GM controls.

    Each row exposes a participant count (cached on the object so the
    template doesn't re-query) and a status badge. Empty list is
    allowed and rendered with a placeholder.

    The ``story_ideas`` queryset is passed through so the GM's NEW
    ENCOUNTER form can offer story-arc selection. Players never see
    the form (read_only branch) so the queryset is harmless to ship.
    """
    if request.user.is_superuser:
        encounters = Encounter.objects.all().prefetch_related("participants")
    else:
        encounters = (
            Encounter.objects.filter(
                participants__character__owner=request.user
            )
            .distinct()
            .prefetch_related("participants")
        )
    enriched = []
    for enc in encounters:
        enc.participant_count = enc.participants.count()
        enriched.append(enc)

    # Story ideas only relevant to the GM's NEW ENCOUNTER form, but
    # the template guards on user.is_superuser so this is harmless to
    # populate unconditionally.
    story_ideas = StoryIdea.objects.all().only("id", "title").order_by(
        "-pinned", "-updated_at"
    )

    return render(
        request,
        "combat/list.html",
        {
            "encounters": enriched,
            "story_ideas": story_ideas,
            # v0.15.8 — list page now distinguishes "GM ONLY" vs the
            # player view via the same ``is_gm`` flag the encounter
            # detail uses, for consistency. The sub-strip text shifts
            # to acknowledge that v0.15.8 players can take turns,
            # not just spectate.
            "is_gm": request.user.is_superuser,
        },
    )


@login_required
def encounter_page(request, pk):
    """GET — render a single encounter with its participants and log.

    v0.15.7 — superusers retain full GM access; players are admitted
    to a read-only spectator view iff they own at least one Character
    that is currently a Participant of this encounter. Anyone else
    gets HTTP 403 (we deliberately use 403 rather than 404 — the
    information leak is intentional, since the WS-level rejection
    uses the same boundary and being consistent across both surfaces
    is simpler than performing 403/404 oblivious lookups).

    v0.15.8 — the binary ``read_only`` flag is replaced with a more
    nuanced model: every participant is annotated with
    ``p.can_control`` (the user owns this row's character, OR is a
    superuser). Templates gate per-row controls on that flag and
    page-level controls on ``is_gm``. Players reaching the page
    therefore see their *own* character's full action panel
    (equip / cover / attack / dodge / full-defense / willpower /
    self-conditions) while every other row stays spectator-only.

    Spawn sources are passed in directly as querysets / lists; the
    template iterates them inside the "+ ADD PARTICIPANT" panel
    (which itself is gated on ``is_gm``).
    """
    encounter = get_object_or_404(Encounter, pk=pk)

    # Authorisation gate. Superusers always pass. Player participants
    # are admitted to drive their own row(s); everybody else is
    # rejected.
    is_gm = request.user.is_superuser
    if not is_gm:
        is_player_participant = encounter.participants.filter(
            character__owner=request.user
        ).exists()
        if not is_player_participant:
            return HttpResponseForbidden("ACCESS DENIED.")

    # Participants split by faction so the three columns can each
    # iterate their own slice without re-filtering in the template.
    # ``select_related("character")`` so the per-row ``can_control``
    # check below doesn't fan out to N+1 owner lookups.
    participants = list(
        encounter.participants.select_related("character")
        .all()
        .order_by("position_order", "id")
    )

    # v0.15.5 — annotate each participant with derived chips for the
    # row template. Done in Python (rather than a template tag) so
    # _wound_penalty / _condition_*_modifier stay co-located with the
    # rest of the resolver helpers.
    for p in participants:
        wp = _wound_penalty(p)
        cond_atk = _condition_attack_modifier(p)
        cond_def = _condition_defense_modifier(p)
        p.wound_penalty = wp
        p.attack_modifier_total = wp + cond_atk
        p.defense_modifier_total = cond_def

        # v0.15.9 — pre-computed numeric attack-pool breakdown for
        # the row template. The skill is auto-picked from the
        # equipped weapon's category (empty ``weapon_skill_name``
        # triggers the fallback inside ``_attack_preview``). GM
        # modifier is zero in the preview — the row's <input>
        # ``mod-{id}`` updates the live total client-side without
        # a re-render.
        p.attack_preview = _attack_preview(
            p, p.weapon_data, gm_modifier=0, weapon_skill_name=""
        )

        # v0.15.8 — controllability flag. Superusers control every
        # row; players control only rows whose character they own.
        # NPCs and mooks have no character FK, so players can never
        # control them — only the GM.
        p.can_control = _can_control_participant(request.user, p)

        # v0.15.14 — burst-fire eligibility (firearm has auto_capable).
        # Drives the FIRE MODE select on the attack form: when False,
        # the select stays disabled and only the SINGLE option is
        # rendered. Server re-validates on submit so a tampered POST
        # that smuggles burst_mode=long onto a Hand Gun simply
        # downgrades to single (and a system row notes the attempt).
        p.weapon_auto_capable = _weapon_is_auto_capable(p.weapon_data)

        # v0.15.15 — ammo annotations. ``ammo_state`` is the current
        # rounds-in-magazine (``None`` if no ammo tag is set);
        # ``ammo_max`` is the catalogue magazine size from the
        # snapshotted ``weapon_data`` (zero for non-firearm / mook /
        # legacy data). The MAG x/y indicator on the row renders only
        # when ``ammo_max > 0``; empty / partial states colour-code
        # via inline conditionals in the template.
        p.ammo_state = _ammo_state(p)
        try:
            p.ammo_max = int((p.weapon_data or {}).get("magazine", 0) or 0)
        except (TypeError, ValueError):
            p.ammo_max = 0
        if p.ammo_max < 0:
            p.ammo_max = 0

        # v0.15.16 — off-hand annotations. ``has_offhand`` drives the
        # DUAL ATTACK checkbox visibility on the attack form;
        # ``offhand_ammo_state`` / ``offhand_ammo_max`` feed a
        # parallel MAG indicator next to the off-hand weapon name.
        # ``is_ambidextrous`` is computed from the actor's merit
        # entries (canonical M2M + legacy JSON) and drives the
        # checkbox label between "−2 dice off-hand" vs
        # "AMBIDEXTROUS — no penalty".
        p.has_offhand = bool(p.offhand_weapon_data)
        p.offhand_ammo_state = _offhand_ammo_state(p)
        try:
            p.offhand_ammo_max = int(
                (p.offhand_weapon_data or {}).get("magazine", 0) or 0
            )
        except (TypeError, ValueError):
            p.offhand_ammo_max = 0
        if p.offhand_ammo_max < 0:
            p.offhand_ammo_max = 0
        p.is_ambidextrous = _has_ambidextrous_merit(p)

        # v0.15.17 — Gun Fu annotations. ``gun_fu_remaining`` drives the
        # GUN FU input visibility on the attack form (only rendered when
        # > 0 AND the equipped weapon is a firearm). Rating + used are
        # surfaced for the muted REMAINING THIS SESSION caption.
        # ``_gun_fu_state`` returns (0, 0, 0) for mooks, NPCs, and
        # non-soldier characters, so the input is suppressed for every
        # ineligible row without an explicit conditional in the template.
        gf_rating, gf_used, gf_remaining = _gun_fu_state(p)
        p.gun_fu_rating = gf_rating
        p.gun_fu_used = gf_used
        p.gun_fu_remaining = gf_remaining
        # ``ammo_pct`` drives the colour tier of the indicator —
        # green ≥50%, amber 25–50%, red <25% / 0. Pre-computed in
        # Python so the template stays declarative.
        if p.ammo_max > 0 and p.ammo_state is not None:
            p.ammo_pct = (p.ammo_state * 100) // p.ammo_max
        else:
            p.ammo_pct = 0
        if p.ammo_max > 0 and p.ammo_state is not None:
            if p.ammo_state == 0:
                p.ammo_color = "red"
            elif p.ammo_pct < 25:
                p.ammo_color = "red"
            elif p.ammo_pct < 50:
                p.ammo_color = "amber"
            else:
                p.ammo_color = "green"
        else:
            p.ammo_color = ""

        # v0.15.14 — aim state for the row banner. ``aim_state`` is
        # ``(target_id, turns)`` or ``None``; resolve target_name in a
        # second pass below so the banner can display
        # ``AIMING: <target_name> (+<turns>/3)``. The banner has its
        # own × CANCEL AIM button posting to clear_condition with
        # condition=aiming_at, which the existing prefix-aware clear
        # handler already strips.
        p.aim_state = _aim_state(p)
        p.aim_target_name = None  # filled in on a second pass below

        # Pills for the header — color-coded (red for incapacitated,
        # cyan for stances, amber for ordinary status conditions).
        pills = []
        for tag in (p.conditions or []):
            if tag == "incapacitated":
                pills.append((tag, CONDITION_DEFS[tag]["label"], "red"))
            elif tag == "defense_full":
                pills.append((tag, "FULL DEF", "cyan"))
            elif tag == "dodge_pending":
                pills.append((tag, "DODGE PENDING", "cyan"))
            elif tag.startswith("dodging:"):
                try:
                    n = int(tag.split(":", 1)[1])
                except (ValueError, IndexError):
                    n = 0
                pills.append((tag, f"DODGING ({n})", "cyan"))
            elif tag in CONDITION_DEFS:
                pills.append((tag, CONDITION_DEFS[tag]["label"], "amber"))
            else:
                # Unknown tag — render uppercased free-text.
                pills.append((tag, tag.upper(), "amber"))
        p.condition_pills = pills

        # Options for the "ADD CONDITION" sub-form — exclude stance
        # tags (set via dedicated buttons) and ``dodge_pending`` (set
        # only by the dodge resolver itself).
        p.condition_options = [
            (key, defn["label"])
            for key, defn in CONDITION_DEFS.items()
            if key not in _STANCE_TAGS
        ]

    # v0.15.14 — second pass to resolve aim target names. Done after
    # the main loop so we can do a O(N) lookup against the same
    # participants list (rather than another DB round-trip per row).
    pid_to_name = {p.id: p.name for p in participants}
    for p in participants:
        if p.aim_state is None:
            continue
        target_id, _turns = p.aim_state
        p.aim_target_name = pid_to_name.get(target_id)

    by_faction = {
        "player_or_ally": [p for p in participants if p.faction in ("player", "ally")],
        "hostile": [p for p in participants if p.faction == "hostile"],
        "neutral": [p for p in participants if p.faction == "neutral"],
    }

    # Initiative tracker: ordered by score descending with id as the
    # deterministic tiebreak, nulls last so unrolled participants sink
    # to the bottom of the tracker.
    ordered_participants = list(
        encounter.participants.select_related("character").order_by(
            F("initiative_score").desc(nulls_last=True), "id"
        )
    )
    # v0.15.8 — propagate the per-row controllability flag to the
    # initiative tracker too, so the per-row ROLL button can gate on
    # it without reaching back into the participants list.
    for p in ordered_participants:
        p.can_control = _can_control_participant(request.user, p)

    # Active participant pointer (denormalised on the encounter; may be
    # None during setup or after a clear).
    active_participant_obj = None
    if encounter.active_participant_id:
        for p in participants:
            if p.id == encounter.active_participant_id:
                active_participant_obj = p
                break

    # How many participants still need to roll initiative — the START
    # button gates on this being zero, and the template surfaces it as
    # a muted note while non-zero.
    unrolled_count = encounter.participants.filter(
        initiative_score__isnull=True
    ).count()

    log_entries = encounter.log_entries.order_by("sequence")

    # Spawn sources for the "+ ADD PARTICIPANT" form.
    available_characters = Character.objects.select_related("owner").order_by("name")
    # Include both regular (player-assigned) NPCs and agency dossiers.
    # Group for the template so the GM can pick from any agency, not
    # just the ones currently in play. Hidden dossiers stay GM-only —
    # the encounter page itself is GM-gated for the ADD PARTICIPANT
    # block via the is_gm template flag.
    available_npcs = (
        NPC.objects.select_related("agency")
        .order_by("agency__name", "name")
    )
    npcs_by_group = {}
    for n in available_npcs:
        if n.is_npc_dossier:
            label = f"DOSSIER · {n.agency.name.upper()}" if n.agency else "DOSSIER · UNASSIGNED"
        else:
            label = "PLAYER NPCS"
        npcs_by_group.setdefault(label, []).append(n)
    # Stable ordering: PLAYER NPCS first, then dossier groups alphabetically.
    npcs_grouped = []
    if "PLAYER NPCS" in npcs_by_group:
        npcs_grouped.append(("PLAYER NPCS", npcs_by_group.pop("PLAYER NPCS")))
    for label in sorted(npcs_by_group.keys()):
        npcs_grouped.append((label, npcs_by_group[label]))
    settings_obj = SiteSettings.load()
    combat_npc_templates = settings_obj.get_combat_npcs()

    # Group templates by category for the optgroup layout.
    combat_npcs_by_cat = {}
    for entry in combat_npc_templates:
        cat = entry.get("category", "other") or "other"
        combat_npcs_by_cat.setdefault(cat, []).append(entry)

    # v0.15.4 catalogues for the equip-weapon / equip-armor /
    # set-cover sub-forms on each participant row. Cover entries are
    # also grouped by tier so the per-state <optgroup> layout stays
    # readable.
    weapon_choices = settings_obj.get_weapons()
    armor_choices = settings_obj.get_armor()
    cover_choices = settings_obj.get_cover()
    cover_by_tier = {}
    for entry in cover_choices:
        tier = entry.get("tier", "other") or "other"
        cover_by_tier.setdefault(tier, []).append(entry)

    # Attack action gate — the per-row ATTACK form is only rendered
    # when the encounter is active and we know which participant is
    # currently up.
    attack_eligible = (
        encounter.status == "active"
        and encounter.active_participant_id is not None
    )

    # v0.15.7 — story-arc options for the EDIT form's <select>.
    # Cheap unconditional fetch (titles only, ordered by pinned
    # then recency) — the player branch hides the form entirely so
    # this queryset costs us nothing in the read-only path.
    story_ideas = StoryIdea.objects.all().only("id", "title").order_by(
        "-pinned", "-updated_at"
    )

    # v0.15.8 — does the current user have at least one controllable
    # participant in this encounter? Drives the role-aware kicker
    # banner (PLAYER VIEW vs READ-ONLY SPECTATOR). For the GM this is
    # always True; the kicker is suppressed for the GM regardless.
    has_any_control = any(p.can_control for p in ordered_participants)

    return render(
        request,
        "combat/encounter.html",
        {
            "encounter": encounter,
            "participants": participants,
            "participants_by_faction": by_faction,
            "ordered_participants": ordered_participants,
            "active_participant_obj": active_participant_obj,
            "unrolled_count": unrolled_count,
            "log_entries": log_entries,
            "available_characters": available_characters,
            "available_npcs": available_npcs,
            "npcs_grouped": npcs_grouped,
            "combat_npc_templates": combat_npc_templates,
            "combat_npcs_by_cat": combat_npcs_by_cat,
            "weapon_choices": weapon_choices,
            "armor_choices": armor_choices,
            "cover_choices": cover_choices,
            "cover_by_tier": cover_by_tier,
            "attack_eligible": attack_eligible,
            "story_ideas": story_ideas,
            # v0.15.8 — replace the binary ``read_only`` flag with a
            # role-aware pair: ``is_gm`` gates page-level GM controls
            # (encounter CRUD, lifecycle, ADD PARTICIPANT). Per-row
            # action gating is handled by ``p.can_control`` on each
            # participant. ``has_any_control`` drives the
            # PLAYER-VIEW vs SPECTATOR kicker.
            "is_gm": is_gm,
            "has_any_control": has_any_control,
        },
    )


# ---------------------------------------------------------------------------
# Encounter CRUD (POST)
# ---------------------------------------------------------------------------


def _resolve_story_idea(raw):
    """Map a raw form value to a StoryIdea instance or None.

    Accepts blank string / "0" / a missing entry — all of which mean
    "no link". Any other value is looked up as a primary key; a miss
    falls back to ``None`` rather than raising, so a stale form post
    never 500s. Returns the StoryIdea instance or ``None``.
    """
    if not raw or str(raw).strip() in ("", "0"):
        return None
    try:
        return StoryIdea.objects.filter(pk=int(raw)).first()
    except (TypeError, ValueError):
        return None


@login_required
@_gm_only
@csrf_protect
def encounter_create(request):
    """POST — create a new encounter and seed its log with a system row.

    v0.15.7: also reads optional ``story_idea_id`` from the form. Blank
    or unknown values fall through to ``None`` (no story arc).
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    story_idea = _resolve_story_idea(request.POST.get("story_idea_id"))
    encounter = Encounter.objects.create(
        title=request.POST.get("title", "").strip() or "Untitled Encounter",
        scene_description=request.POST.get("scene_description", "").strip(),
        location_text=request.POST.get("location_text", "").strip(),
        gm=request.user,
        status="setup",
        round_number=0,
        story_idea=story_idea,
    )
    # First log row is always sequence=1; seed via the helper so the
    # invariant holds even if a future migration backfills history.
    _log(encounter, "system", "Encounter created.")
    return redirect("combat:detail", pk=encounter.pk)


@login_required
@_gm_only
@csrf_protect
def encounter_update(request, pk):
    """POST — update an encounter's metadata (title / scene / location).

    v0.15.7: also accepts ``story_idea_id`` to (re)link or clear the
    story-arc association. Only mutated when the field is actually
    present in the POST body so unrelated update paths don't
    accidentally drop the link.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    encounter = get_object_or_404(Encounter, pk=pk)
    encounter.title = request.POST.get("title", encounter.title).strip() or encounter.title
    encounter.scene_description = request.POST.get(
        "scene_description", encounter.scene_description
    ).strip()
    encounter.location_text = request.POST.get(
        "location_text", encounter.location_text
    ).strip()
    update_fields = ["title", "scene_description", "location_text", "updated_at"]
    if "story_idea_id" in request.POST:
        encounter.story_idea = _resolve_story_idea(request.POST.get("story_idea_id"))
        update_fields.append("story_idea")
    encounter.save(update_fields=update_fields)

    _log(encounter, "system", "Encounter metadata updated.")
    return redirect("combat:detail", pk=encounter.pk)


@login_required
@_gm_only
@csrf_protect
def encounter_delete(request, pk):
    """POST — hard-delete an encounter.

    CASCADE on Participant + CombatLog handles the dependents; no
    separate cleanup is needed.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    encounter = get_object_or_404(Encounter, pk=pk)
    encounter.delete()
    return redirect("combat:list")


# ---------------------------------------------------------------------------
# Participant CRUD (POST)
# ---------------------------------------------------------------------------


@login_required
@_gm_only
@csrf_protect
def participant_add(request, pk):
    """POST — spawn a participant from one of three sources.

    ``kind`` form field selects the source. Each branch denormalises
    enough state into the Participant row that the encounter remains
    consistent even if the underlying Character / NPC / catalogue
    entry is later edited or deleted.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    encounter = get_object_or_404(Encounter, pk=pk)
    kind = request.POST.get("kind", "")

    # Allocate the next position slot up front; identical for all branches.
    next_pos = (
        encounter.participants.aggregate(Max("position_order"))["position_order__max"] or 0
    ) + 1

    participant = None

    if kind == "character":
        character_id = request.POST.get("character_id")
        if not character_id:
            return redirect("combat:detail", pk=encounter.pk)
        character = get_object_or_404(Character, pk=character_id)

        # Health = Size + Stamina (resistance.physical). Default 7 if
        # the JSON shape is missing the keys (legacy / partial sheets).
        try:
            stamina = int(character.attributes["resistance"]["physical"])
            health_max = int(character.size) + stamina
        except (KeyError, TypeError, ValueError):
            health_max = 7

        # Willpower = Resolve (resistance.mental) + Composure (resistance.social).
        try:
            willpower_max = int(character.attributes["resistance"]["mental"]) + int(
                character.attributes["resistance"]["social"]
            )
        except (KeyError, TypeError, ValueError):
            willpower_max = 0

        faction = request.POST.get("faction", "player")
        # v0.15.12 — copy the canonical sheet's CURRENT damage / willpower /
        # mental load into the snapshot. A wounded character entering combat
        # arrives with their wounds already on the row; wound penalties apply
        # from join. ``health_max`` is recomputed above (Size + Stamina) so a
        # Stamina change since the last fight is reflected on join.
        participant = Participant.objects.create(
            encounter=encounter,
            participant_kind="character",
            character=character,
            name=character.name,
            faction=faction,
            health_max=health_max,
            health_bashing=character.health_bashing,
            health_lethal=character.health_lethal,
            health_aggravated=character.health_aggravated,
            willpower_max=willpower_max,
            willpower_current=character.willpower_current,
            mental_load=getattr(character, "mental_load", 0),
            position_order=next_pos,
        )

    elif kind == "npc":
        npc_id = request.POST.get("npc_id")
        if not npc_id:
            return redirect("combat:detail", pk=encounter.pk)
        npc_obj = get_object_or_404(NPC, pk=npc_id)

        try:
            stamina = int(npc_obj.attributes["resistance"]["physical"])
            health_max = int(npc_obj.size) + stamina
        except (KeyError, TypeError, ValueError):
            health_max = 7

        try:
            willpower_max = int(npc_obj.attributes["resistance"]["mental"]) + int(
                npc_obj.attributes["resistance"]["social"]
            )
        except (KeyError, TypeError, ValueError):
            willpower_max = 0

        faction = request.POST.get("faction", "hostile")
        # v0.15.12 — same join-time canonical-state copy for NPCs. NPCs share
        # the health_bashing/lethal/aggravated/willpower_current/mental_load
        # field shape with Character, so the snapshot fills identically.
        participant = Participant.objects.create(
            encounter=encounter,
            participant_kind="npc",
            npc=npc_obj,
            name=npc_obj.name,
            faction=faction,
            health_max=health_max,
            health_bashing=npc_obj.health_bashing,
            health_lethal=npc_obj.health_lethal,
            health_aggravated=npc_obj.health_aggravated,
            willpower_max=willpower_max,
            willpower_current=npc_obj.willpower_current,
            mental_load=getattr(npc_obj, "mental_load", 0),
            position_order=next_pos,
        )

    elif kind == "template":
        template_name = request.POST.get("template_name", "")
        if not template_name:
            return redirect("combat:detail", pk=encounter.pk)

        # Catalogue lookup is by name. The catalogue is a JSON list of
        # dicts on SiteSettings; enforce-uniqueness happens in the
        # editor, so the first match wins here.
        templates = SiteSettings.load().get_combat_npcs()
        entry = next((t for t in templates if t.get("name") == template_name), None)
        if entry is None:
            return redirect("combat:detail", pk=encounter.pk)

        faction = request.POST.get("faction", "hostile")
        participant = Participant.objects.create(
            encounter=encounter,
            participant_kind="mook",
            name=entry.get("name", "Mook"),
            faction=faction,
            mook_combat_pool=_safe_int(entry.get("combat_pool"), 0),
            mook_defense=_safe_int(entry.get("defense"), 0),
            health_max=_safe_int(entry.get("health_max"), 7),
            mook_armor_rating=entry.get("armor_rating", "") or "",
            weapon_name=entry.get("weapon", "") or "",
            notes=entry.get("notes", "") or "",
            position_order=next_pos,
        )

    if participant is not None:
        # v0.15.12 — surface the joining row's current health / willpower so
        # the timeline shows pre-existing wounds (mooks always join at full
        # since the catalogue carries no damage state).
        health_at_join = {
            "bashing": participant.health_bashing,
            "lethal": participant.health_lethal,
            "aggravated": participant.health_aggravated,
            "willpower_current": participant.willpower_current,
            "willpower_max": participant.willpower_max,
        }
        _log(
            encounter,
            "system",
            f"Added {participant.name} ({participant.faction}) to encounter.",
            participant_id=participant.pk,
            participant_kind=participant.participant_kind,
            faction=participant.faction,
            health_at_join=health_at_join,
        )

    return redirect("combat:detail", pk=encounter.pk)


@login_required
@_gm_only
@csrf_protect
def participant_remove(request, pk, participant_id):
    """POST — drop a participant from the encounter.

    Captures the display name first so the log row remains
    human-readable after the row is deleted.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    encounter = get_object_or_404(Encounter, pk=pk)
    participant = get_object_or_404(Participant, pk=participant_id, encounter=encounter)
    name = participant.name
    participant.delete()
    _log(
        encounter,
        "system",
        f"Removed {name} from encounter.",
        participant_id=participant_id,
    )
    return redirect("combat:detail", pk=encounter.pk)


# ---------------------------------------------------------------------------
# Initiative + turn advance (POST)  — v0.15.3
# ---------------------------------------------------------------------------


@login_required
@_gm_or_owner()
@csrf_protect
def roll_initiative(request, pk, participant_id):
    """POST — roll initiative for a single participant.

    Rejected as a no-op redirect when the encounter is already
    concluded (rolls into a closed encounter make no game sense and
    would corrupt the timeline).

    v0.15.8 — players can roll initiative for their own character.
    The decorator enforces ownership; NPCs and mooks remain GM-only
    by virtue of having no ``character`` FK.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    encounter = get_object_or_404(Encounter, pk=pk)
    if encounter.status == "concluded":
        # Silent no-op; the UI hides the button in this state but
        # defensive against direct POSTs from a stale tab.
        return redirect("combat:detail", pk=encounter.pk)

    participant = get_object_or_404(Participant, pk=participant_id, encounter=encounter)

    modifier, d10, score = _compute_initiative(participant)
    participant.initiative_roll = d10
    participant.initiative_score = score
    participant.save(update_fields=["initiative_roll", "initiative_score"])

    _log(
        encounter,
        "initiative",
        f"{participant.name} rolled initiative: {modifier} + {d10} = {score}.",
        participant_id=participant.pk,
        modifier=modifier,
        d10=d10,
        score=score,
    )
    return redirect("combat:detail", pk=encounter.pk)


@login_required
@_gm_only
@csrf_protect
def roll_initiative_all(request, pk):
    """POST — roll initiative for every unrolled participant in one pass.

    Each participant gets its own ``initiative`` log row so the
    timeline shows the whole party's individual results, then a
    single ``system`` row summarises the batch. The encounter's
    ``initiative_order`` is rebuilt from the resulting scores
    (descending, id ascending) so START can pick the first actor
    deterministically.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    encounter = get_object_or_404(Encounter, pk=pk)
    if encounter.status == "concluded":
        return redirect("combat:detail", pk=encounter.pk)

    unrolled = list(
        encounter.participants.filter(initiative_score__isnull=True).order_by("id")
    )
    count = 0
    for participant in unrolled:
        modifier, d10, score = _compute_initiative(participant)
        participant.initiative_roll = d10
        participant.initiative_score = score
        participant.save(update_fields=["initiative_roll", "initiative_score"])
        _log(
            encounter,
            "initiative",
            f"{participant.name} rolled initiative: {modifier} + {d10} = {score}.",
            participant_id=participant.pk,
            modifier=modifier,
            d10=d10,
            score=score,
        )
        count += 1

    # Rebuild the order pointer over every rolled participant —
    # safer than appending to whatever was there before, since
    # participants may have been added since the last sort.
    encounter.initiative_order = [
        p.id
        for p in encounter.participants.exclude(initiative_score__isnull=True).order_by(
            "-initiative_score", "id"
        )
    ]
    encounter.save(update_fields=["initiative_order", "updated_at"])

    _log(
        encounter,
        "system",
        f"Initiative rolled for {count} participants.",
        count=count,
    )
    return redirect("combat:detail", pk=encounter.pk)


@login_required
@_gm_only
@csrf_protect
def clear_initiative(request, pk):
    """POST — wipe initiative rolls and reset the encounter to setup.

    Bulk-clears scores / rolls on every participant, drops the order
    pointer and active participant, and (if the encounter was active)
    rolls back to ``status='setup'`` with ``round_number=0`` and the
    timing fields nulled out. ``acted_this_round`` is also reset so a
    fresh roll-all + start cycle starts cleanly.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    encounter = get_object_or_404(Encounter, pk=pk)

    # Bulk update all participants in one query.
    encounter.participants.update(
        initiative_score=None,
        initiative_roll=None,
        acted_this_round=False,
    )

    encounter.initiative_order = []
    encounter.active_participant_id = None
    if encounter.status == "active":
        # Revert lifecycle to setup so the GM can re-roll cleanly.
        encounter.status = "setup"
        encounter.round_number = 0
        encounter.started_at = None
        encounter.ended_at = None
    encounter.save(
        update_fields=[
            "initiative_order",
            "active_participant_id",
            "status",
            "round_number",
            "started_at",
            "ended_at",
            "updated_at",
        ]
    )

    _log(encounter, "system", "Initiative cleared. Encounter reset to setup.")
    return redirect("combat:detail", pk=encounter.pk)


@login_required
@_gm_only
@csrf_protect
def start_encounter(request, pk):
    """POST — transition the encounter from setup to active.

    Refuses to start unless every participant has rolled initiative
    (a flash message names the count). Rebuilds ``initiative_order``
    from the live scores, sets ``active_participant_id`` to the top of
    the order, marks ``round_number=1`` and stamps ``started_at``.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    encounter = get_object_or_404(Encounter, pk=pk)
    if encounter.status != "setup":
        return redirect("combat:detail", pk=encounter.pk)

    unrolled_count = encounter.participants.filter(
        initiative_score__isnull=True
    ).count()
    if unrolled_count > 0:
        messages.error(
            request,
            f"{unrolled_count} participants have not rolled initiative yet.",
        )
        return redirect("combat:detail", pk=encounter.pk)

    ordered = list(
        encounter.participants.order_by("-initiative_score", "id")
    )
    if not ordered:
        # Edge case: empty encounter. Refuse silently — there is no
        # valid "first actor" to point at.
        messages.error(request, "Cannot start an encounter with no participants.")
        return redirect("combat:detail", pk=encounter.pk)

    encounter.initiative_order = [p.id for p in ordered]
    encounter.active_participant_id = ordered[0].id
    encounter.status = "active"
    encounter.round_number = 1
    encounter.started_at = timezone.now()
    encounter.save(
        update_fields=[
            "initiative_order",
            "active_participant_id",
            "status",
            "round_number",
            "started_at",
            "updated_at",
        ]
    )

    # Reset acted_this_round on every participant for the fresh round.
    encounter.participants.update(acted_this_round=False)

    # v0.15.15 — fill magazines for every Character / NPC participant
    # whose snapshotted ``weapon_data`` is a firearm with a positive
    # ``magazine`` value AND who doesn't already carry an ``ammo:*``
    # tag from an earlier equip. This handles the case where a
    # participant was equipped during setup (the equip-weapon hook
    # already filled the mag in that path; we just don't double-fill
    # here). Mooks are skipped — their weapon is a free-text catalogue
    # label, not a snapshot dict, so there's no per-participant ammo
    # state to manage.
    filled_count = 0
    for p in encounter.participants.all():
        if p.participant_kind not in ("character", "npc"):
            continue
        wd = p.weapon_data or {}
        if wd.get("category") != "firearm":
            continue
        try:
            mag = int(wd.get("magazine", 0) or 0)
        except (TypeError, ValueError):
            mag = 0
        if mag <= 0:
            continue
        if _ammo_state(p) is not None:
            # Already has an ammo tag (set on equip). Don't reset —
            # equipping mid-setup with a partial use case isn't on the
            # table in v0.15.15, but if some path put a tag on we
            # respect it rather than silently top up.
            continue
        _set_ammo(p, mag)
        p.save(update_fields=["conditions"])
        filled_count += 1

    _log(
        encounter,
        "system",
        f"Encounter started — round 1, {ordered[0].name} acts first.",
        first_participant_id=ordered[0].id,
    )
    if filled_count > 0:
        _log(
            encounter,
            "system",
            f"Magazines filled at combat start ({filled_count} participants).",
            filled_count=filled_count,
        )
    return redirect("combat:detail", pk=encounter.pk)


def _advance_turn_pointer(encounter):
    """Step the active pointer forward one slot, rolling the round
    over if we're at the end of initiative_order. Writes the
    appropriate log rows (turn_advance / round_advance / stance-clear
    system row / dodge_pending carry-over). Idempotent for malformed
    states — returns early on missing order.

    Pulled out of next_turn so pass_turn can reuse it after recording
    its own log message. Called only from inside an active encounter.
    """
    order = list(encounter.initiative_order or [])
    if not order:
        return

    current_id = encounter.active_participant_id
    if current_id is not None:
        Participant.objects.filter(pk=current_id, encounter=encounter).update(
            acted_this_round=True
        )

    try:
        idx = order.index(current_id)
    except ValueError:
        idx = -1

    if idx >= len(order) - 1:
        encounter.round_number += 1
        encounter.participants.update(acted_this_round=False)
        cleared_any = False
        # v0.15.14 — also strip aiming_at:* tags at the round
        # boundary. Aim does not survive a round roll (the WoD 2.0
        # action economy treats each round as a clean reset for
        # turn-cost actions). The strip is folded into the same
        # save() that nukes defense_full and dodging:N so we don't
        # double-write per row.
        for p in encounter.participants.all():
            new_conds = [
                c for c in (p.conditions or [])
                if c != "defense_full"
                and not c.startswith("dodging:")
                and not c.startswith("aiming_at:")
            ]
            if new_conds != (p.conditions or []):
                p.conditions = new_conds
                p.save(update_fields=["conditions"])
                cleared_any = True
        next_id = order[0]
        encounter.active_participant_id = next_id
        encounter.save(
            update_fields=["round_number", "active_participant_id", "updated_at"]
        )
        _log(
            encounter,
            "round_advance",
            f"Round {encounter.round_number} begins.",
            round_number=encounter.round_number,
        )
        if cleared_any:
            # Phrasing covers both stance and aim clears — the
            # template reader doesn't need to know which fired.
            _log(encounter, "system", "Defensive stances and aim cleared at round boundary.")
    else:
        next_id = order[idx + 1]
        encounter.active_participant_id = next_id
        encounter.save(update_fields=["active_participant_id", "updated_at"])
        next_p = encounter.participants.filter(pk=next_id).first()
        next_name = next_p.name if next_p else f"#{next_id}"
        _log(
            encounter,
            "turn_advance",
            f"Turn passes to {next_name}.",
            participant_id=next_id,
        )

    # Out-of-turn dodge carry-over.
    new_active = encounter.participants.filter(
        pk=encounter.active_participant_id
    ).first()
    if new_active is not None and "dodge_pending" in (new_active.conditions or []):
        new_active.conditions = [
            c for c in (new_active.conditions or []) if c != "dodge_pending"
        ]
        new_active.acted_this_round = True
        new_active.save(update_fields=["conditions", "acted_this_round"])
        _log(
            encounter,
            "system",
            f"{new_active.name}: dodge_pending consumed — turn skipped.",
            target_participant_id=new_active.id,
        )


@login_required
@_gm_only
@csrf_protect
def next_turn(request, pk):
    """POST — advance the active participant pointer.

    If the current participant is the last in ``initiative_order`` the
    round rolls over: ``round_number`` increments, every participant's
    ``acted_this_round`` flag is reset, defensive stances
    (``defense_full``, ``dodging:N``) are cleared across the board,
    and the pointer wraps to the top of the order (logged as
    ``round_advance`` plus a ``system`` row noting the stance clear).
    Otherwise the pointer steps forward one slot and a
    ``turn_advance`` row is written.

    v0.15.5 also handles **out-of-turn dodge** carry-over: when a
    participant becomes active and they're carrying a
    ``dodge_pending`` tag from a previous round's dodge, they're
    immediately marked acted-this-round and the tag is stripped (the
    eaten turn is paid).
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    encounter = get_object_or_404(Encounter, pk=pk)
    if encounter.status != "active":
        return redirect("combat:detail", pk=encounter.pk)

    _advance_turn_pointer(encounter)
    return redirect("combat:detail", pk=encounter.pk)


@login_required
@_gm_or_owner()
@csrf_protect
def pass_turn(request, pk, participant_id):
    """POST — active participant voluntarily ends their turn.

    Player or GM-driven. Logs a ``pass_turn`` row with the participant's
    name, then auto-advances the pointer (same logic as ``next_turn``).
    Rejects if the encounter isn't active or if the calling participant
    isn't the current active actor — players cannot pass for someone
    else.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    encounter = get_object_or_404(Encounter, pk=pk)
    if encounter.status != "active":
        return redirect("combat:detail", pk=encounter.pk)

    participant = get_object_or_404(
        Participant, pk=participant_id, encounter=encounter
    )
    if participant.id != encounter.active_participant_id:
        messages.error(request, "It is not this participant's turn.")
        return redirect("combat:detail", pk=encounter.pk)

    _log(
        encounter,
        "pass_turn",
        f"{participant.name} passes their turn.",
        participant_id=participant.pk,
    )
    _advance_turn_pointer(encounter)
    return redirect("combat:detail", pk=encounter.pk)


@login_required
@_gm_or_owner()
@csrf_protect
def aim(request, pk, participant_id):
    """POST — active participant spends the turn aiming at a target.

    Aim grants ``+1`` cumulative dice on the next attack against the
    aimed target, stackable up to ``+3`` over consecutive aim turns
    (re-aiming the same target). State lives as a single condition
    tag of shape ``aiming_at:<target_id>:<turns>`` so no schema change
    is needed.

    Lifecycle (consumed / cleared by):

    * ``attack`` → consumed when target matches; silently broken when
      target differs.
    * ``full_defense`` / ``dodge`` → strip aim (defending breaks aim).
    * ``_apply_damage`` → strip aim when the aimer takes damage.
    * ``next_turn`` round-roll → strip every aim tag across the
      encounter (aim does not survive a round boundary).

    Mirrors the ``full_defense`` / ``dodge`` pattern: aim eats the
    actor's turn (sets ``acted_this_round=True``) but does NOT
    auto-advance the pointer — the GM clicks NEXT TURN to actually
    pass the turn. Only ``pass_turn`` auto-advances.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    encounter = get_object_or_404(Encounter, pk=pk)
    if encounter.status != "active":
        messages.error(request, "Cannot aim outside an active encounter.")
        return redirect("combat:detail", pk=encounter.pk)

    participant = get_object_or_404(
        Participant, pk=participant_id, encounter=encounter
    )

    # Aim costs the turn — must be the active actor. Out-of-turn aim
    # would let a participant re-aim someone else's turn, which has
    # no game-mechanical meaning.
    if encounter.active_participant_id != participant.id:
        messages.error(request, "Aim must be taken on your own turn.")
        return redirect("combat:detail", pk=encounter.pk)

    target_id_raw = request.POST.get("target_id")
    if not target_id_raw:
        messages.error(request, "Pick a target to aim at.")
        return redirect("combat:detail", pk=encounter.pk)
    try:
        target_id = int(target_id_raw)
    except (TypeError, ValueError):
        messages.error(request, "Invalid target.")
        return redirect("combat:detail", pk=encounter.pk)

    # Reject self-aim (no game meaning, easy to misclick).
    if target_id == participant.id:
        messages.error(request, "Cannot aim at self.")
        return redirect("combat:detail", pk=encounter.pk)

    target = Participant.objects.filter(
        pk=target_id, encounter=encounter
    ).first()
    if target is None:
        messages.error(request, "Target not found in this encounter.")
        return redirect("combat:detail", pk=encounter.pk)

    # Compute the next aim state. Re-aiming the same target stacks
    # turns up to a hard cap of 3; switching targets resets to 1.
    prev_state = _aim_state(participant)
    if prev_state is not None and prev_state[0] == target_id:
        new_turns_uncapped = prev_state[1] + 1
    else:
        new_turns_uncapped = 1
    turns_clamped = (new_turns_uncapped > 3)
    new_turns = min(3, new_turns_uncapped)

    # Strip any old aim tag, then append the fresh one. Calling
    # _strip_aim mutates participant.conditions in place; we then
    # append the new tag and persist.
    _strip_aim(participant)
    new_conds = list(participant.conditions or [])
    new_conds.append(f"aiming_at:{target_id}:{new_turns}")
    participant.conditions = new_conds
    participant.acted_this_round = True
    participant.save(update_fields=["conditions", "acted_this_round"])

    _log(
        encounter,
        "aim",
        (
            f"{participant.name} aims at {target.name} "
            f"(turn {new_turns}/3, +{new_turns} dice on next attack)."
        ),
        actor_participant_id=participant.id,
        target_participant_id=target_id,
        turns=new_turns,
        bonus=new_turns,
        turns_clamped=turns_clamped,
    )
    return redirect("combat:detail", pk=encounter.pk)


@login_required
@_gm_only
@csrf_protect
def end_encounter(request, pk):
    """POST — conclude the encounter.

    Sets status to ``concluded``, clears the active pointer (no one
    is acting anymore), and stamps ``ended_at``. Redirects to the
    encounter list so the GM lands on a clean surface — the detail
    page is still reachable for post-mortem review.

    v0.15.12 — when ending, the snapshot health / willpower / mental_load
    of every Character / NPC participant is committed back to the
    canonical sheet so damage taken in combat is visible elsewhere in
    the app afterwards. Mooks have no sheet and are skipped. The GM
    can opt out of the commit by ticking the ``skip_commit`` checkbox
    on the END form (test fights, dream sequences, "what if" scenarios).

    Snapshot wins on commit. If the GM manually edited the canonical
    sheet during combat (e.g. healed 1 lethal via the character page),
    that edit will be overwritten when end_encounter runs. Use the
    skip_commit checkbox to preserve the canonical state.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    encounter = get_object_or_404(Encounter, pk=pk)
    rounds = encounter.round_number
    encounter.status = "concluded"
    encounter.active_participant_id = None
    encounter.ended_at = timezone.now()
    encounter.save(
        update_fields=[
            "status",
            "active_participant_id",
            "ended_at",
            "updated_at",
        ]
    )

    # ---- v0.15.12 — bidirectional sheet commit -------------------------------
    skip_commit = request.POST.get("skip_commit") == "1"

    if skip_commit:
        # Single system row, no per-participant work. The encounter is
        # concluded as normal but canonical sheets are untouched.
        _log(
            encounter,
            "system",
            "End-of-combat sheet commit SKIPPED by GM. "
            "Damage stays in encounter snapshot only.",
            skipped=True,
        )
    else:
        commit_count = 0
        for participant in encounter.participants.all():
            # Mooks have no canonical sheet to commit to.
            if participant.participant_kind == "mook":
                continue

            # FK can be None when the underlying sheet was deleted mid-fight
            # (FK has on_delete=SET_NULL). Nothing to write back to.
            target = None
            if participant.participant_kind == "character":
                target = participant.character
            elif participant.participant_kind == "npc":
                target = participant.npc
            if target is None:
                continue

            # Read the canonical pre-commit state for the audit-trail
            # ``before`` payload BEFORE we overwrite anything.
            before = {
                "bashing": target.health_bashing,
                "lethal": target.health_lethal,
                "aggravated": target.health_aggravated,
                "willpower_current": target.willpower_current,
                "mental_load": getattr(target, "mental_load", 0),
            }
            after = {
                "bashing": participant.health_bashing,
                "lethal": participant.health_lethal,
                "aggravated": participant.health_aggravated,
                "willpower_current": participant.willpower_current,
                "mental_load": participant.mental_load,
            }

            # Write the snapshot fields back to the canonical row. Use
            # update_fields= for an efficient narrow UPDATE — we don't want
            # to round-trip every column on every commit.
            target.health_bashing = participant.health_bashing
            target.health_lethal = participant.health_lethal
            target.health_aggravated = participant.health_aggravated
            target.willpower_current = participant.willpower_current
            target.mental_load = participant.mental_load
            target.save(
                update_fields=[
                    "health_bashing",
                    "health_lethal",
                    "health_aggravated",
                    "willpower_current",
                    "mental_load",
                ]
            )

            # Per-participant audit row. Goes through _log() so the WS
            # broadcast hook fires and any open clients see it live.
            _log(
                encounter,
                "health_commit",
                (
                    f"{participant.name}: "
                    f"HP {participant.health_bashing}/"
                    f"{participant.health_lethal}/"
                    f"{participant.health_aggravated} · "
                    f"WP {participant.willpower_current}/"
                    f"{participant.willpower_max} · "
                    f"ML {participant.mental_load} → committed to sheet."
                ),
                participant_id=participant.pk,
                participant_kind=participant.participant_kind,
                before=before,
                after=after,
            )
            commit_count += 1

        # Final summary row so the timeline has a single clean marker for
        # "this is when the sheets were synced".
        _log(
            encounter,
            "system",
            f"Sheet commits: {commit_count} participants updated.",
            count=commit_count,
            skipped=False,
        )

    _log(
        encounter,
        "system",
        f"Encounter concluded after {rounds} round(s).",
        rounds=rounds,
    )
    return redirect("combat:list")


# ---------------------------------------------------------------------------
# Equip + cover (POST)  — v0.15.4
# ---------------------------------------------------------------------------


@login_required
@_gm_or_owner()
@csrf_protect
def equip_weapon(request, pk, participant_id):
    """POST — equip / unequip a weapon on a participant.

    ``weapon_name`` form field is matched against
    ``SiteSettings.get_weapons()`` (first match wins). Empty / not
    found clears the slot. The matched catalogue entry is *snapshotted*
    into ``participant.weapon_data`` so a later catalogue edit doesn't
    retroactively rewrite the in-flight encounter.

    v0.15.8 — players may equip on their own character row.

    v0.15.15 — equipping a firearm with a catalogue ``magazine > 0``
    auto-fills the magazine to capacity via the ``ammo:<N>`` condition
    tag. Equipping a non-firearm (or unequipping) strips any stale
    ``ammo:*`` tag. Mooks aren't routed through this view in v0.15.15
    so the ammo plumbing only touches Character / NPC participants.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    encounter = get_object_or_404(Encounter, pk=pk)
    participant = get_object_or_404(
        Participant, pk=participant_id, encounter=encounter
    )

    name = request.POST.get("weapon_name", "").strip()

    if not name:
        # Empty submission = unequip. Strip any ammo tag so the next
        # equip starts from a clean slate.
        participant.weapon_name = ""
        participant.weapon_data = {}
        _strip_ammo(participant)
        participant.save(update_fields=["weapon_name", "weapon_data", "conditions"])
        _log(
            encounter,
            "weapon_change",
            f"{participant.name} unequipped weapon.",
            participant_id=participant.pk,
            weapon_name="",
            magazine_full=False,
        )
        return redirect("combat:detail", pk=encounter.pk)

    weapons = SiteSettings.load().get_weapons()
    entry = next((w for w in weapons if w.get("name") == name), None)

    if entry is None:
        # Unknown weapon — also clears the slot, so a stale POST
        # doesn't leave a half-equipped state behind.
        participant.weapon_name = ""
        participant.weapon_data = {}
        _strip_ammo(participant)
        participant.save(update_fields=["weapon_name", "weapon_data", "conditions"])
        _log(
            encounter,
            "weapon_change",
            f"{participant.name} unequipped weapon.",
            participant_id=participant.pk,
            weapon_name="",
            magazine_full=False,
        )
        return redirect("combat:detail", pk=encounter.pk)

    # Snapshot the full entry — defensive shallow copy so later
    # mutations on the catalogue list don't bleed in.
    participant.weapon_name = entry.get("name", "")
    participant.weapon_data = dict(entry)

    # v0.15.15 — fill the magazine on equip if the catalogue entry is a
    # firearm with a positive magazine size. Otherwise strip any stale
    # ammo tag (covers the swap-from-firearm-to-melee path).
    mag = 0
    if entry.get("category") == "firearm":
        try:
            mag = int(entry.get("magazine", 0) or 0)
        except (TypeError, ValueError):
            mag = 0
    if mag > 0:
        _set_ammo(participant, mag)
        magazine_full = True
    else:
        _strip_ammo(participant)
        magazine_full = False

    participant.save(update_fields=["weapon_name", "weapon_data", "conditions"])

    _log(
        encounter,
        "weapon_change",
        f"{participant.name} equipped {participant.weapon_name}.",
        participant_id=participant.pk,
        weapon_name=participant.weapon_name,
        magazine=mag,
        magazine_full=magazine_full,
    )
    return redirect("combat:detail", pk=encounter.pk)


@login_required
@_gm_or_owner()
@csrf_protect
def equip_offhand(request, pk, participant_id):
    """POST — equip / unequip an off-hand weapon on a participant.

    v0.15.16 — mirror of :func:`equip_weapon`, but writes to the
    ``offhand_weapon_name`` / ``offhand_weapon_data`` fields and uses
    the ``offhand_ammo:N`` parallel-tag helpers.

    Form field ``weapon_name`` is matched against
    ``SiteSettings.get_weapons()`` (first match wins). Empty / not
    found clears the off-hand slot and strips any
    ``offhand_ammo:*`` tag.

    Off-hand ammo lifecycle in v0.15.16:
      * SET on equip if catalogue entry is a firearm with ``magazine > 0``.
      * STRIPPED on un-equip / non-firearm equip.
      * NOT refillable mid-fight — there's no off-hand reload action
        in v0.15.16. Run dry → empty until re-equipped. Re-equipping
        the same weapon counts as "swap out / swap in" and refills.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    encounter = get_object_or_404(Encounter, pk=pk)
    participant = get_object_or_404(
        Participant, pk=participant_id, encounter=encounter
    )

    name = request.POST.get("weapon_name", "").strip()

    if not name:
        # Empty submission = unequip. Strip any off-hand ammo tag so a
        # later equip starts from a clean slate.
        participant.offhand_weapon_name = ""
        participant.offhand_weapon_data = {}
        _strip_offhand_ammo(participant)
        participant.save(update_fields=[
            "offhand_weapon_name", "offhand_weapon_data", "conditions",
        ])
        _log(
            encounter,
            "weapon_change",
            f"{participant.name} unequipped off-hand weapon.",
            participant_id=participant.pk,
            offhand=True,
            weapon_name="",
            magazine_full=False,
        )
        return redirect("combat:detail", pk=encounter.pk)

    weapons = SiteSettings.load().get_weapons()
    entry = next((w for w in weapons if w.get("name") == name), None)

    if entry is None:
        # Unknown weapon — also clears the slot.
        participant.offhand_weapon_name = ""
        participant.offhand_weapon_data = {}
        _strip_offhand_ammo(participant)
        participant.save(update_fields=[
            "offhand_weapon_name", "offhand_weapon_data", "conditions",
        ])
        _log(
            encounter,
            "weapon_change",
            f"{participant.name} unequipped off-hand weapon.",
            participant_id=participant.pk,
            offhand=True,
            weapon_name="",
            magazine_full=False,
        )
        return redirect("combat:detail", pk=encounter.pk)

    # Snapshot the catalogue entry so a later edit doesn't retroactively
    # mutate the in-flight encounter.
    participant.offhand_weapon_name = entry.get("name", "")
    participant.offhand_weapon_data = dict(entry)

    # Fill the off-hand magazine on equip if the catalogue entry is a
    # firearm with a positive magazine size. Otherwise strip any stale
    # off-hand ammo tag (covers the swap-firearm-to-melee path).
    mag = 0
    if entry.get("category") == "firearm":
        try:
            mag = int(entry.get("magazine", 0) or 0)
        except (TypeError, ValueError):
            mag = 0
    if mag > 0:
        _set_offhand_ammo(participant, mag)
        magazine_full = True
    else:
        _strip_offhand_ammo(participant)
        magazine_full = False

    participant.save(update_fields=[
        "offhand_weapon_name", "offhand_weapon_data", "conditions",
    ])

    _log(
        encounter,
        "weapon_change",
        f"{participant.name} equipped {participant.offhand_weapon_name} "
        f"(off-hand).",
        participant_id=participant.pk,
        offhand=True,
        weapon_name=participant.offhand_weapon_name,
        magazine=mag,
        magazine_full=magazine_full,
    )
    return redirect("combat:detail", pk=encounter.pk)


@login_required
@_gm_or_owner()
@csrf_protect
def equip_armor(request, pk, participant_id):
    """POST — equip / unequip armor on a participant.

    Mirror of ``equip_weapon`` against ``SiteSettings.get_armor()``.
    Snapshot semantics are the same — catalogue edits do not mutate
    in-flight encounters.

    v0.15.8 — players may equip on their own character row.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    encounter = get_object_or_404(Encounter, pk=pk)
    participant = get_object_or_404(
        Participant, pk=participant_id, encounter=encounter
    )

    name = request.POST.get("armor_name", "").strip()

    if not name:
        participant.armor_name = ""
        participant.armor_data = {}
        participant.save(update_fields=["armor_name", "armor_data"])
        _log(
            encounter,
            "armor_change",
            f"{participant.name} unequipped armor.",
            participant_id=participant.pk,
            armor_name="",
        )
        return redirect("combat:detail", pk=encounter.pk)

    armors = SiteSettings.load().get_armor()
    entry = next((a for a in armors if a.get("name") == name), None)

    if entry is None:
        participant.armor_name = ""
        participant.armor_data = {}
        participant.save(update_fields=["armor_name", "armor_data"])
        _log(
            encounter,
            "armor_change",
            f"{participant.name} unequipped armor.",
            participant_id=participant.pk,
            armor_name="",
        )
        return redirect("combat:detail", pk=encounter.pk)

    participant.armor_name = entry.get("name", "")
    participant.armor_data = dict(entry)
    participant.save(update_fields=["armor_name", "armor_data"])

    _log(
        encounter,
        "armor_change",
        f"{participant.name} equipped {participant.armor_name}.",
        participant_id=participant.pk,
        armor_name=participant.armor_name,
    )
    return redirect("combat:detail", pk=encounter.pk)


@login_required
@_gm_or_owner()
@csrf_protect
def set_cover(request, pk, participant_id):
    """POST — update a participant's cover state.

    ``cover_state`` (none/light/heavy/full) drives the attacker
    penalty in the resolver. ``cover_entry_name`` is an optional
    catalogue lookup against ``SiteSettings.get_cover()`` — when it
    matches, durability + health from the entry seed the cover's
    breach track (see v0.14.65 cover-destruction rules).

    v0.15.8 — players may set cover on their own character row.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    encounter = get_object_or_404(Encounter, pk=pk)
    participant = get_object_or_404(
        Participant, pk=participant_id, encounter=encounter
    )

    valid_states = {"none", "light", "heavy", "full"}
    state = request.POST.get("cover_state", "none").strip().lower()
    if state not in valid_states:
        state = "none"

    entry_name = request.POST.get("cover_entry_name", "").strip()

    if state == "none":
        # Clearing cover wipes the catalogue link too.
        participant.cover_state = "none"
        participant.cover_entry_name = ""
        participant.cover_durability = None
        participant.cover_health = None
        participant.save(update_fields=[
            "cover_state",
            "cover_entry_name",
            "cover_durability",
            "cover_health",
        ])
        _log(
            encounter,
            "cover_change",
            f"{participant.name} cleared cover.",
            participant_id=participant.pk,
            cover_state="none",
        )
        return redirect("combat:detail", pk=encounter.pk)

    # Optional catalogue lookup — populates durability + health when
    # a match is found.
    durability = None
    health = None
    if entry_name:
        cover_catalogue = SiteSettings.load().get_cover()
        entry = next(
            (c for c in cover_catalogue if c.get("name") == entry_name),
            None,
        )
        if entry is not None:
            durability = _safe_int(entry.get("durability"), 0) or None
            health = _safe_int(entry.get("health"), 0) or None
        else:
            # Entry name supplied but not found — keep the free-text
            # name so the GM's intent isn't lost, but leave breach
            # stats null.
            pass

    participant.cover_state = state
    participant.cover_entry_name = entry_name
    participant.cover_durability = durability
    participant.cover_health = health
    participant.save(update_fields=[
        "cover_state",
        "cover_entry_name",
        "cover_durability",
        "cover_health",
    ])

    label = (
        f"{participant.name} entered {state} cover ({entry_name})."
        if entry_name
        else f"{participant.name} entered {state} cover."
    )
    _log(
        encounter,
        "cover_change",
        label,
        participant_id=participant.pk,
        cover_state=state,
        cover_entry_name=entry_name,
    )
    return redirect("combat:detail", pk=encounter.pk)


# ---------------------------------------------------------------------------
# Attack resolution (POST)  — v0.15.5 (full WoD attack loop)
# ---------------------------------------------------------------------------


def _resolve_single_attack(
    encounter, attacker, target, *,
    weapon_data, weapon_name, weapon_skill,
    attack_pool, gm_modifier_int, wound_pen, cond_atk_mod,
    spent_wp, applied_specs, spec_bonus,
    msg_tail, msg_tail_parts,
    spread_index=0, spread_penalty=0,
    extra_payload=None,
    bonus_successes=0,
):
    """Resolve one attack roll against one target, write log rows.

    Extracted from ``attack`` so v0.15.14 burst spread can call this
    helper once for the primary target and once per extra spread
    target. ``attack_pool`` is the *pre-defense, pre-cover* pool for
    this specific target — the burst-spread orchestrator computes a
    different pool per extra (primary gets aim + burst, extras get
    burst minus the spread penalty index).

    ``spread_index`` is 0 for the primary attack, 1+ for extras (used
    for log-message phrasing and a ``data.spread_index`` payload key).
    ``extra_payload`` lets the caller stuff additional structured data
    into the row (e.g. burst_mode, burst_bonus, aim_bonus).

    ``bonus_successes`` (v0.15.17) is added to the rolled success count
    *post-roll* (after defense/cover/dice but before damage math). It
    drives the Gun Fu merit's "free auto successes" effect. The roll
    itself still happens — auto-successes do not bypass full cover, do
    not turn a missed roll into a hit when defense + cover already
    blocked the entire pool, and do not double as the dice. They simply
    bump the success tally before damage is calculated. A miss with
    bonus successes upgrades to a hit (the per-target log row carries
    ``gun_fu_bonus_successes`` so the timeline reflects the source).

    Returns nothing — log rows are the side effect. The caller is
    responsible for the encounter-level redirect and any cross-target
    summary row.
    """
    extra_payload = dict(extra_payload or {})
    spread_tail = (
        f" (BURST SPREAD #{spread_index})" if spread_index > 0 else ""
    )
    # v0.15.17 — Gun Fu tail. Appended after spread_tail so per-target
    # rows read e.g. "(WP+3) (BURST SPREAD #2) (GUN FU +1 SUCC)".
    gun_fu_bonus = max(0, int(bonus_successes or 0))
    gun_fu_tail = (
        f" (GUN FU +{gun_fu_bonus} SUCC)" if gun_fu_bonus > 0 else ""
    )
    # Always present on the payload so timeline filters can group on
    # the key without checking for absence (zero is a valid value
    # meaning "no Gun Fu spend on this target").
    extra_payload.setdefault("gun_fu_bonus_successes", gun_fu_bonus)

    defense = _compute_defense(target)
    cover_pen = _cover_penalty(target.cover_state)

    # v0.15.19 — record the X-again threshold up-front so it's
    # available for both the full-cover blocked branch and the rolled
    # branches without re-deriving it. Reading from the snapshot keeps
    # the action's recorded threshold stable even if the catalogue
    # is edited mid-encounter.
    weapon_again_for_log = _clamp_again_local(
        (weapon_data or {}).get("again", 10) if weapon_data else 10
    )

    base_payload = dict(
        actor_participant_id=attacker.id,
        target_participant_id=target.id,
        attack_pool=attack_pool,
        defense=defense,
        gm_modifier=gm_modifier_int,
        weapon_name=weapon_name,
        weapon_skill=weapon_skill,
        wound_penalty=wound_pen,
        condition_attack_modifier=cond_atk_mod,
        spent_willpower=spent_wp,
        willpower_after=attacker.willpower_current,
        applied_specs=applied_specs,
        spec_bonus=spec_bonus,
        spread_index=spread_index,
        spread_penalty=spread_penalty,
        # v0.15.19 — X-again explosion threshold for this attack roll
        # (one of {8, 9, 10}). Surfaces in the timeline so the GM can
        # read which trigger value was active per row, even after the
        # catalogue has been re-tuned.
        weapon_again=weapon_again_for_log,
    )
    base_payload.update(extra_payload)

    # ---- Full cover short-circuit -----------------------------------------
    if cover_pen == "BLOCKED":
        # v0.15.17 — Gun Fu auto-successes do NOT bypass full cover.
        # Cover state blocks the shot entirely; if the bullet can't
        # reach the target the merit's free successes are wasted on
        # this target. The caller still records the spend on the
        # character (we don't refund here — the player declared the
        # split before resolution).
        payload = dict(base_payload)
        payload.update(
            outcome="blocked_by_cover",
            cover_state=target.cover_state,
            successes=0,
        )
        _log(
            encounter,
            "attack",
            f"{attacker.name} → {target.name}: BLOCKED BY FULL COVER."
            + msg_tail + spread_tail + gun_fu_tail,
            **payload,
        )
        return

    final_pool = max(0, attack_pool - defense - cover_pen)
    # v0.15.19 — pass the X-again threshold from the equipped weapon's
    # snapshot (cached as ``weapon_again_for_log`` above). Default 10
    # covers legacy snapshots captured before v0.15.19, plus every
    # non-firearm row (which carries 10 by hydration anyway).
    successes, dice = _roll_pool(
        final_pool, again_threshold=weapon_again_for_log
    )
    # v0.15.17 — apply Gun Fu auto-successes to the success tally
    # post-roll. ``rolled_successes`` is preserved on the payload so
    # the timeline can show the dice contribution separately from the
    # merit contribution.
    rolled_successes = successes
    successes = rolled_successes + gun_fu_bonus

    # ---- Miss --------------------------------------------------------------
    if successes == 0:
        payload = dict(base_payload)
        payload.update(
            outcome="miss",
            cover_pen=cover_pen,
            final_pool=final_pool,
            dice=dice,
            successes=0,
            rolled_successes=rolled_successes,
        )
        _log(
            encounter,
            "attack",
            f"{attacker.name} attacks {target.name}: missed."
            + msg_tail + spread_tail + gun_fu_tail,
            **payload,
        )
        return

    # ---- Hit ---------------------------------------------------------------
    weapon_amount, damage_type_from_field = _parse_weapon_damage(
        weapon_data.get("damage", "")
    )
    damage_type = (
        weapon_data.get("damage_type")
        or damage_type_from_field
        or "L"
    ).upper()
    if damage_type not in ("B", "L", "A"):
        damage_type = "L"

    raw_damage = successes + weapon_amount

    if target.participant_kind == "mook":
        rating = target.mook_armor_rating or ""
    else:
        rating = (target.armor_data or {}).get("rating", "")
    b_armor, l_armor = _parse_armor_rating(rating)
    if damage_type == "B":
        armor_reduction = b_armor
    elif damage_type == "L":
        armor_reduction = l_armor
    else:
        armor_reduction = 0  # aggravated bypasses armor

    final_damage = max(0, raw_damage - armor_reduction)
    type_label = {"B": "bashing", "L": "lethal", "A": "aggravated"}[damage_type]

    applied, upgraded, overflow = _apply_damage(target, final_damage, damage_type)

    payload = dict(base_payload)
    payload.update(
        outcome="hit",
        cover_pen=cover_pen,
        final_pool=final_pool,
        dice=dice,
        successes=successes,
        rolled_successes=rolled_successes,
        raw_damage=raw_damage,
        weapon_damage=weapon_amount,
        armor_reduction=armor_reduction,
        final_damage=final_damage,
        damage_type=damage_type,
        applied=applied,
        upgrades=upgraded,
        overflow=overflow,
    )

    _log(
        encounter,
        "attack",
        f"{attacker.name} hits {target.name} for {final_damage} {type_label} damage."
        + msg_tail + spread_tail + gun_fu_tail,
        **payload,
    )
    _log(
        encounter,
        "health_change",
        f"{target.name} takes {final_damage} {type_label} damage."
        + spread_tail + gun_fu_tail,
        **payload,
    )

    # Auto-incapacitation: if the total damage now fills the track,
    # tag the target and emit a condition_set row. Idempotent.
    total_dmg = (
        target.health_bashing + target.health_lethal + target.health_aggravated
    )
    if total_dmg >= target.health_max and not _has_condition(target, "incapacitated"):
        new_conds = list(target.conditions or [])
        new_conds.append("incapacitated")
        target.conditions = new_conds
        target.save(update_fields=["conditions"])
        _log(
            encounter,
            "condition_set",
            f"{target.name} is INCAPACITATED.",
            target_participant_id=target.id,
            condition="incapacitated",
        )


@login_required
@_gm_or_owner("attacker_id")
@csrf_protect
def attack(request, pk, attacker_id):
    """POST — resolve a single attack from active participant → target.

    Guard rails:

    * Encounter must be ``active``.
    * Attacker must be the active participant per the initiative
      tracker (so the GM driving the buttons can't accidentally roll
      out of turn).
    * Target must exist in the same encounter.
    * Self-targeting is rejected (zero useful gameplay, easy to
      misclick).
    * Faction is **not** checked — PvP is intentional.

    v0.15.8 — players may attack as their own character when it's
    their turn. The decorator gates ownership of the *attacker*; the
    active-turn check below is what lets PvP through (any character
    can target any other participant once their initiative slot is
    up). The target side is unconstrained beyond "not self" so a
    player firing on another player goes through cleanly.

    v0.15.5 layers wound penalties, condition modifiers, willpower
    spend, full damage track upgrade, and auto-incapacitation onto the
    v0.15.4 pipeline. The resolver writes one or two log rows
    depending on the outcome (plus an optional ``condition_set`` row
    when the target gets KO'd).

    v0.15.14 — three new mechanics layered on top:

    * **AIM** — if the attacker has an ``aiming_at:<target_id>:<turns>``
      tag and the chosen primary target matches, ``+turns`` dice are
      added to the primary pool and the aim is consumed. If the chosen
      primary target differs, the aim is silently broken (no bonus).
    * **Burst fire** — ``burst_mode`` form field (single / short /
      medium / long) adds 0 / +1 / +2 / +3 dice. Server falls back to
      single-fire (with a ``system`` log row) when the equipped weapon
      is not auto-capable.
    * **Autofire spread** — medium / long bursts can engage extra
      targets via ``extra_target_ids``. Each extra resolves a separate
      attack roll at ``-1 * spread_index`` cumulative dice penalty.
      Aim only applies to the primary target — extras don't get the
      aim bonus.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    encounter = get_object_or_404(Encounter, pk=pk)
    if encounter.status != "active":
        messages.error(request, "Cannot attack outside an active encounter.")
        return redirect("combat:detail", pk=encounter.pk)

    attacker = get_object_or_404(
        Participant, pk=attacker_id, encounter=encounter
    )
    if encounter.active_participant_id != attacker.id:
        messages.error(
            request,
            "Only the active participant can attack.",
        )
        return redirect("combat:detail", pk=encounter.pk)

    target_id_raw = request.POST.get("target_id")
    if not target_id_raw:
        messages.error(request, "Pick a target.")
        return redirect("combat:detail", pk=encounter.pk)
    target = get_object_or_404(
        Participant, pk=target_id_raw, encounter=encounter
    )
    if target.id == attacker.id:
        messages.error(request, "Cannot attack self.")
        return redirect("combat:detail", pk=encounter.pk)

    gm_modifier_int = _safe_int(request.POST.get("gm_modifier"), 0)
    weapon_skill = request.POST.get("weapon_skill", "").strip()

    # Willpower spend gating — checkbox sets the value to "1". Defensive
    # against the (UI-impossible but POST-craftable) zero-willpower
    # spend so we never decrement below zero.
    spend_wp_requested = bool(request.POST.get("spend_willpower"))
    spent_wp = spend_wp_requested and (attacker.willpower_current or 0) > 0

    weapon_data = attacker.weapon_data or {}
    weapon_name = attacker.weapon_name or "(unarmed)"

    # v0.15.9 — auto-pick weapon skill when omitted.
    if not weapon_skill:
        weapon_skill = _weapon_skill_for(weapon_data)

    # v0.15.10 — validate player-picked specialisations against
    # the actor's actual sheet.
    submitted_specs = request.POST.getlist("applied_specs")
    allowed_specs = _specialisations_for_skill(attacker, weapon_skill)
    allowed_lower = {s.lower(): s for s in allowed_specs}
    applied_specs = []
    seen = set()
    for raw_name in submitted_specs:
        if not isinstance(raw_name, str):
            continue
        key = raw_name.strip().lower()
        if not key or key in seen:
            continue
        if key in allowed_lower:
            applied_specs.append(allowed_lower[key])
            seen.add(key)
    spec_bonus = len(applied_specs)

    # v0.15.14 — burst-fire mode resolution. Reject anything outside
    # the four canonical values and, when the equipped weapon isn't
    # auto-capable, silently downgrade non-single modes to single
    # (with a system log row noting the attempt). Keeps a tampered
    # POST from sneaking +3 dice onto a Hand Gun.
    burst_mode_raw = request.POST.get("burst_mode", "single")
    burst_mode = burst_mode_raw if burst_mode_raw in BURST_BONUSES else "single"
    auto_capable = _weapon_is_auto_capable(weapon_data)
    if burst_mode != "single" and not auto_capable:
        _log(
            encounter,
            "system",
            f"{attacker.name} attempted {burst_mode} burst but weapon "
            f"is not auto-capable — fired single.",
            actor_participant_id=attacker.id,
            attempted_burst_mode=burst_mode,
            weapon_name=weapon_name,
        )
        burst_mode = "single"

    # v0.15.15 — ammo gating. Only firearms with a positive catalogue
    # magazine size carry an ammo tag. Mooks (no weapon_data dict) and
    # non-firearms / pre-v0.15.15 catalogue rows skip this whole block
    # and behave the way they did in v0.15.14.
    is_firearm = weapon_data.get("category") == "firearm"
    try:
        mag_size = int(weapon_data.get("magazine", 0) or 0)
    except (TypeError, ValueError):
        mag_size = 0
    ammo_tracked = bool(is_firearm and mag_size > 0)
    burst_downgraded_due_to_ammo = False
    ammo_before = None
    if ammo_tracked:
        ammo_before = _ammo_state(attacker)
        # Defensive: a firearm-equipped participant who somehow lost
        # their ammo tag (legacy data, condition-clear collision)
        # collapses to "no ammo on file" — we treat that as zero so
        # the OUT-OF-AMMO branch below fires rather than silently
        # rolling. The reload action will set them straight.
        if ammo_before is None:
            ammo_before = 0
        rounds_required = BURST_AMMO_COST.get(burst_mode, 1)
        if ammo_before == 0:
            messages.error(
                request,
                f"OUT OF AMMO — RELOAD FIRST. ({weapon_name})",
            )
            _log(
                encounter,
                "system",
                f"{attacker.name} attempted to fire {weapon_name} with empty mag — rejected.",
                actor_participant_id=attacker.id,
                weapon_name=weapon_name,
                attempted_burst_mode=burst_mode,
            )
            return redirect("combat:detail", pk=encounter.pk)
        if ammo_before < rounds_required:
            # Insufficient ammo for the requested burst — silently
            # downgrade to single. The shooter still pulls a trigger
            # rather than getting a hard "not enough rounds" rejection,
            # mirroring the auto_capable downgrade pattern above.
            _log(
                encounter,
                "system",
                f"Insufficient ammo for {burst_mode} burst "
                f"({ammo_before}/{rounds_required}) — fired single instead.",
                actor_participant_id=attacker.id,
                weapon_name=weapon_name,
                attempted_burst_mode=burst_mode,
                ammo_available=ammo_before,
                ammo_required=rounds_required,
            )
            burst_mode = "single"
            burst_downgraded_due_to_ammo = True

    burst_bonus = BURST_BONUSES[burst_mode]
    rounds_fired = BURST_AMMO_COST[burst_mode] if ammo_tracked else 0

    # v0.15.14 — aim consumption. We always strip the aim tag at the
    # end of an attack (whether consumed or broken), but the bonus
    # only applies when the primary target matches the aimed target.
    aim_state = _aim_state(attacker)
    aim_bonus = 0
    aim_consumed = False
    aim_broken = False
    aim_target_id_for_log = None
    if aim_state is not None:
        aim_target_id_for_log, aim_turns = aim_state
        if aim_target_id_for_log == target.id:
            aim_bonus = aim_turns
            aim_consumed = True
        else:
            aim_broken = True

    # v0.15.5 + v0.15.10 — full pool composition (base + wound + cond +
    # WP + spec). v0.15.14 — adds burst bonus + aim bonus on the
    # PRIMARY target. Extras don't get aim; extras do get burst bonus.
    wound_pen = _wound_penalty(attacker)
    cond_atk_mod = _condition_attack_modifier(attacker)
    base_pool_no_burst = _actor_total_pool(
        attacker, weapon_data, gm_modifier_int, weapon_skill,
        spend_willpower=spent_wp,
        applied_specialisations=applied_specs,
    )
    primary_pool = base_pool_no_burst + burst_bonus + aim_bonus

    # Decrement willpower and persist if the spend went through.
    # Done *before* any roll so payload's willpower_after is accurate.
    if spent_wp:
        attacker.willpower_current = max(0, (attacker.willpower_current or 0) - 1)
        attacker.save(update_fields=["willpower_current"])

    # v0.15.10/v0.15.14 — pre-built log message tail (WP / SPEC / AIM /
    # BURST suffixes). Centralised so blocked / miss / hit all read
    # identically. Spread tail is added inside _resolve_single_attack.
    msg_tail_parts = []
    if spent_wp:
        msg_tail_parts.append("WP+3")
    if applied_specs:
        msg_tail_parts.append("+SPEC: " + ", ".join(applied_specs))
    if aim_bonus:
        msg_tail_parts.append(f"+{aim_bonus} AIM")
    if burst_bonus:
        msg_tail_parts.append(f"+{burst_bonus} BURST")
    msg_tail = (" (" + " | ".join(msg_tail_parts) + ")") if msg_tail_parts else ""

    # v0.15.14 — extra targets for autofire spread. Cap by burst mode,
    # filter against this encounter's participants, drop self / primary
    # / duplicates, order deterministically by (position_order, id).
    extras = []
    extras_total = 0
    spread_max = BURST_MAX_EXTRAS.get(burst_mode, 0)
    if spread_max > 0:
        raw_extras = request.POST.getlist("extra_target_ids")
        # Deduplicate raw input, preserving order of first appearance.
        seen_extra_ids = set()
        candidate_ids = []
        for raw in raw_extras:
            try:
                eid = int(raw)
            except (TypeError, ValueError):
                continue
            if eid in seen_extra_ids:
                continue
            if eid == attacker.id or eid == target.id:
                continue
            seen_extra_ids.add(eid)
            candidate_ids.append(eid)
        if candidate_ids:
            extras = list(
                Participant.objects.filter(
                    pk__in=candidate_ids,
                    encounter=encounter,
                ).order_by("position_order", "id")
            )
            # Cap at the burst mode's max — drop excess silently rather
            # than reject the whole shot.
            if len(extras) > spread_max:
                extras = extras[:spread_max]
            extras_total = len(extras)

    aim_only_on_primary = (extras_total > 0 and aim_bonus > 0)

    # v0.15.15 — compute the post-fire magazine state up-front so the
    # value can be threaded into every per-target log row. The ammo
    # tag is decremented once after the resolver pass (regardless of
    # how many extras are engaged — burst spread fires the same
    # rounds at multiple targets). When ammo isn't tracked the keys
    # stay None / False so the timeline can filter on presence.
    ammo_after = None
    if ammo_tracked:
        ammo_after = max(0, ammo_before - rounds_fired)

    # v0.15.16 — DUAL ATTACK gating. The flag is honoured only when the
    # attacker actually has an off-hand weapon equipped; otherwise the
    # request degrades silently to a single main-hand attack (no flash,
    # no rejection — a tampered POST shouldn't dead-end legitimate
    # gameplay). Logged on every off-hand row so the timeline reads
    # straight without the GM having to puzzle out which slot fired.
    dual_attack_requested = (request.POST.get("dual_attack") == "1")
    has_offhand = bool(attacker.offhand_weapon_data)
    dual_attack = dual_attack_requested and has_offhand
    is_ambidextrous = _has_ambidextrous_merit(attacker) if dual_attack else False
    offhand_penalty = 0 if is_ambidextrous else -2

    # v0.15.17 — Gun Fu spend. Defense-in-depth gating mirrors every
    # eligibility rule in ``_gun_fu_state``:
    #   * Mooks / NPCs / non-soldier characters return remaining=0,
    #     so the player-declared total is clamped to 0 and the merit
    #     never engages.
    #   * Non-firearm equipped main hand zeroes out the spend silently
    #     (Gun Fu is gun combat — a sword swing doesn't use it).
    #   * The cap-at-remaining ``min`` makes a tampered POST harmless;
    #     the player can never spend more than they have on file.
    # Distribution order is fixed: primary (slot 0) → spread extras
    # (slots 1..N) → off-hand (slot N+1). The caller below threads
    # the matching slot index into each ``_resolve_single_attack`` call
    # via the ``bonus_successes`` kwarg.
    gun_fu_uses_requested = max(0, _safe_int(request.POST.get("gun_fu_uses"), 0))
    gun_fu_rating, gun_fu_used, gun_fu_remaining = _gun_fu_state(attacker)
    gun_fu_to_spend = min(gun_fu_uses_requested, gun_fu_remaining)
    if (weapon_data or {}).get("category") != "firearm":
        gun_fu_to_spend = 0
    target_count = 1 + extras_total
    if dual_attack and attacker.offhand_weapon_data:
        target_count += 1
    gun_fu_distribution = _distribute_gun_fu(gun_fu_to_spend, target_count)

    extra_payload = {
        "burst_mode": burst_mode,
        "burst_bonus": burst_bonus,
        "aim_bonus": aim_bonus,
        "aim_consumed": aim_consumed,
        "aim_broken": aim_broken,
        "aim_only_on_primary": aim_only_on_primary,
        "extras_total": extras_total,
        # v0.15.15 — ammo accounting. Present on every attack row so
        # the timeline reads accurately even on legacy / non-firearm
        # attacks (where the values stay None / 0 / False).
        "ammo_tracked": ammo_tracked,
        "ammo_before": ammo_before,
        "ammo_after": ammo_after,
        "rounds_fired": rounds_fired,
        "mag_size": mag_size if ammo_tracked else 0,
        "burst_downgraded_due_to_ammo": burst_downgraded_due_to_ammo,
        # v0.15.16 — dual-wield flags on the main-hand attack row so
        # the timeline filter can paint the pair together. The
        # off-hand row carries ``dual_wield_offhand: True`` plus its
        # own penalty/ambidextrous values.
        "dual_wield": dual_attack,
        "dual_wield_offhand": False,
        "dual_wield_penalty": 0,
        "ambidextrous": is_ambidextrous if dual_attack else False,
        # v0.15.17 — Gun Fu spend metadata. Present on every row so
        # the timeline can read the action-wide spend (``gun_fu_total``)
        # and which slot got the bonus (``gun_fu_bonus_successes`` is
        # set per-row inside ``_resolve_single_attack``).
        "gun_fu_total": gun_fu_to_spend,
        "gun_fu_rating": gun_fu_rating,
    }

    # ---- Primary attack ----------------------------------------------------
    primary_gun_fu = gun_fu_distribution[0] if gun_fu_distribution else 0
    _resolve_single_attack(
        encounter, attacker, target,
        weapon_data=weapon_data,
        weapon_name=weapon_name,
        weapon_skill=weapon_skill,
        attack_pool=primary_pool,
        gm_modifier_int=gm_modifier_int,
        wound_pen=wound_pen,
        cond_atk_mod=cond_atk_mod,
        spent_wp=spent_wp,
        applied_specs=applied_specs,
        spec_bonus=spec_bonus,
        msg_tail=msg_tail,
        msg_tail_parts=msg_tail_parts,
        spread_index=0,
        spread_penalty=0,
        extra_payload=extra_payload,
        bonus_successes=primary_gun_fu,
    )

    # ---- Aim tag housekeeping ---------------------------------------------
    # Strip aim now (whether consumed or broken). Refresh attacker
    # from the DB first because _resolve_single_attack may have run
    # _apply_damage on the target — but _apply_damage operates on
    # the target, not the attacker, so the attacker's conditions
    # are still in-memory clean. We can safely use _strip_aim
    # against our existing instance.
    if aim_consumed or aim_broken:
        if aim_broken:
            _log(
                encounter,
                "system",
                f"{attacker.name}'s aim broken — engaged different target.",
                actor_participant_id=attacker.id,
                aimed_target_id=aim_target_id_for_log,
                actual_target_id=target.id,
            )
        # Re-read the attacker so we don't clobber a willpower
        # decrement that already persisted above.
        attacker.refresh_from_db()
        _strip_aim(attacker)
        attacker.save(update_fields=["conditions"])

    # ---- Spread extras -----------------------------------------------------
    for i, extra_target in enumerate(extras, start=1):
        spread_penalty = i  # cumulative -1, -2, ... per index
        # Extras get the burst bonus but NOT the aim bonus. Spread
        # penalty is subtracted from the pool before defense/cover.
        extra_pool = max(0, base_pool_no_burst + burst_bonus - spread_penalty)
        # v0.15.17 — pull this extra's Gun Fu slot from the
        # distribution. Slot index ``i`` (1-based) maps directly to
        # ``gun_fu_distribution[i]`` because slot 0 is the primary.
        extra_gun_fu = (
            gun_fu_distribution[i] if i < len(gun_fu_distribution) else 0
        )
        _resolve_single_attack(
            encounter, attacker, extra_target,
            weapon_data=weapon_data,
            weapon_name=weapon_name,
            weapon_skill=weapon_skill,
            attack_pool=extra_pool,
            gm_modifier_int=gm_modifier_int,
            wound_pen=wound_pen,
            cond_atk_mod=cond_atk_mod,
            spent_wp=spent_wp,
            applied_specs=applied_specs,
            spec_bonus=spec_bonus,
            msg_tail=msg_tail,
            msg_tail_parts=msg_tail_parts,
            spread_index=i,
            spread_penalty=spread_penalty,
            extra_payload=extra_payload,
            bonus_successes=extra_gun_fu,
        )

    # ---- Ammo decrement (v0.15.15) -----------------------------------------
    # Decrement the magazine once per attack regardless of how many
    # spread targets were engaged — a burst is a single trigger pull
    # that consumes ``rounds_fired`` rounds and can be redirected
    # across N targets within the same burst. Decrement happens after
    # the rolls so payload consistency on the per-target rows is
    # preserved (each row already carries ammo_before / ammo_after).
    # The attacker may have been refreshed during aim housekeeping
    # earlier — re-fetch defensively to avoid stomping on the
    # willpower decrement that already persisted.
    if ammo_tracked:
        attacker.refresh_from_db()
        _set_ammo(attacker, ammo_after)
        attacker.save(update_fields=["conditions"])

    # ---- Burst summary row -------------------------------------------------
    if burst_mode != "single" or extras_total > 0:
        if extras_total > 0:
            summary = (
                f"{attacker.name} unleashed {burst_mode} burst — "
                f"primary: {target.name}, spread: {extras_total} additional "
                f"target(s)."
            )
        else:
            summary = (
                f"{attacker.name} fired {burst_mode} burst at {target.name}."
            )
        _log(
            encounter,
            "system",
            summary,
            actor_participant_id=attacker.id,
            burst_mode=burst_mode,
            extras_total=extras_total,
            primary_target_id=target.id,
            extra_target_ids=[e.id for e in extras],
        )

    # ------------------------------------------------------------------
    # v0.15.16 — DUAL ATTACK off-hand resolution
    # ------------------------------------------------------------------
    # Off-hand fires *after* the main hand (and after any burst spread)
    # against the **same primary target**. Distinct rules for the
    # off-hand attack:
    #
    #   * Off-hand pool = base_pool_no_burst (NO burst bonus, NO aim
    #     bonus, NO WP +3) + off-hand weapon dice + Ambidextrous swing.
    #   * Pool composition is rebuilt from scratch via
    #     ``_actor_total_pool`` against the off-hand ``weapon_data`` so
    #     the off-hand weapon's dice modifier and the auto-picked
    #     off-hand skill are honoured. Wound + condition modifiers
    #     still apply (they're shooter-state, not weapon-state).
    #   * spend_willpower=False: WP was already spent on main hand and
    #     decremented from willpower_current. Re-using it would
    #     double-dip.
    #   * applied_specialisations=[]: spec bonus already counted on
    #     main hand. (A future v0.15.17+ might re-validate specs
    #     against the off-hand's auto-picked skill, but v0.15.16 keeps
    #     it simple.)
    #   * Burst is forced to single — even if the off-hand weapon is
    #     auto-capable, dual-burst gets messy fast and v0.15.16 skips
    #     it. Documented in the rules explainer.
    #   * No autofire spread on off-hand (single-shot only against
    #     primary).
    #   * Defense / cover / armor are recomputed afresh against the
    #     same target inside ``_resolve_single_attack`` — handled
    #     identically to the main hand by the same helper.
    #
    # If the off-hand is a firearm with empty mag we skip the resolve
    # step (logging a system warning) so the main-hand attack still
    # lands cleanly. The ``dual_attack`` form flag is silently ignored
    # when no off-hand is equipped (handled above when computing
    # ``dual_attack`` from ``has_offhand``).
    if dual_attack:
        offhand_data = attacker.offhand_weapon_data or {}
        offhand_name = attacker.offhand_weapon_name or "(off-hand)"
        offhand_skill = _weapon_skill_for(offhand_data)

        # Off-hand ammo gating mirrors main hand but on the parallel tag.
        oh_is_firearm = offhand_data.get("category") == "firearm"
        try:
            oh_mag_size = int(offhand_data.get("magazine", 0) or 0)
        except (TypeError, ValueError):
            oh_mag_size = 0
        oh_ammo_tracked = bool(oh_is_firearm and oh_mag_size > 0)

        oh_ammo_before = None
        oh_ammo_after = None
        skip_offhand_due_to_ammo = False
        if oh_ammo_tracked:
            oh_ammo_before = _offhand_ammo_state(attacker)
            if oh_ammo_before is None:
                oh_ammo_before = 0
            if oh_ammo_before == 0:
                # Off-hand dry — main hand attack already landed; we
                # can't reload mid-action in v0.15.16, so log and skip
                # the off-hand resolution. The dual_wield flag on the
                # main row already signals that an off-hand attack
                # was attempted.
                skip_offhand_due_to_ammo = True
                _log(
                    encounter,
                    "system",
                    f"{attacker.name} dual attack: off-hand out of ammo, "
                    f"skipped.",
                    actor_participant_id=attacker.id,
                    offhand_weapon_name=offhand_name,
                )
            else:
                # v0.15.16 always fires SINGLE off-hand → 1 round.
                oh_ammo_after = max(0, oh_ammo_before - 1)

        if not skip_offhand_due_to_ammo:
            # Compose the off-hand pool. Same wound + condition
            # modifiers as the main hand (shooter state), but rebuilt
            # against the OFF-HAND weapon_data so the right weapon
            # dice modifier lands. No WP +3, no aim bonus, no spec
            # bonus, no burst bonus on the off-hand by design.
            offhand_base_pool = _actor_total_pool(
                attacker,
                offhand_data,
                gm_modifier_int,
                offhand_skill,
                spend_willpower=False,
                applied_specialisations=None,
            )
            offhand_pool = max(0, offhand_base_pool + offhand_penalty)

            # Per-target payload for the off-hand row. ``dual_wield``
            # stays True and ``dual_wield_offhand`` flips so a
            # timeline filter can paint the pair as a single dual
            # action. Off-hand carries its own (independent) ammo
            # accounting via the parallel tag — the main-hand keys
            # already on the row's ``extra_payload`` are NOT re-used
            # so the timeline doesn't get confused about which
            # magazine drained.
            offhand_extra_payload = {
                "dual_wield": True,
                "dual_wield_offhand": True,
                "dual_wield_penalty": offhand_penalty,
                "ambidextrous": is_ambidextrous,
                "burst_mode": "single",
                "burst_bonus": 0,
                "aim_bonus": 0,
                "aim_consumed": False,
                "aim_broken": False,
                "aim_only_on_primary": False,
                "extras_total": 0,
                "ammo_tracked": oh_ammo_tracked,
                "ammo_before": oh_ammo_before,
                "ammo_after": oh_ammo_after,
                "rounds_fired": 1 if oh_ammo_tracked else 0,
                "mag_size": oh_mag_size if oh_ammo_tracked else 0,
                "burst_downgraded_due_to_ammo": False,
                # Surface the off-hand weapon name in the payload so
                # downstream consumers (timeline, WS replay) can read
                # which slot fired without re-walking the participant.
                "offhand_weapon_name": offhand_name,
                # v0.15.17 — Gun Fu metadata mirrors the main-hand row
                # so a dual-wield Gun Fu spend can be reconciled across
                # both rows by the same key.
                "gun_fu_total": gun_fu_to_spend,
                "gun_fu_rating": gun_fu_rating,
            }

            offhand_msg_tail_parts = ["OFF-HAND"]
            if is_ambidextrous:
                offhand_msg_tail_parts.append("AMBIDEXTROUS")
            offhand_msg_tail = (
                " (" + ", ".join(offhand_msg_tail_parts) + ")"
            )

            # v0.15.17 — Gun Fu off-hand slot is the LAST element of
            # the distribution (after primary at slot 0 and any spread
            # extras at slots 1..N). Compute by index; gracefully
            # collapse to 0 if the distribution is empty (defensive).
            offhand_gun_fu = (
                gun_fu_distribution[-1]
                if (gun_fu_distribution and len(gun_fu_distribution) >= 2)
                else 0
            )

            _resolve_single_attack(
                encounter, attacker, target,
                weapon_data=offhand_data,
                weapon_name=offhand_name,
                weapon_skill=offhand_skill,
                attack_pool=offhand_pool,
                gm_modifier_int=gm_modifier_int,
                wound_pen=wound_pen,
                cond_atk_mod=cond_atk_mod,
                spent_wp=False,            # WP already spent on main hand
                applied_specs=[],          # spec bonus already counted
                spec_bonus=0,
                msg_tail=offhand_msg_tail,
                msg_tail_parts=offhand_msg_tail_parts,
                spread_index=0,
                spread_penalty=0,
                extra_payload=offhand_extra_payload,
                bonus_successes=offhand_gun_fu,
            )

            # Decrement off-hand ammo after the resolve. Refresh
            # defensively before saving — earlier housekeeping
            # (willpower / main-hand ammo) may have already
            # round-tripped the attacker through the DB.
            if oh_ammo_tracked:
                attacker.refresh_from_db()
                _set_offhand_ammo(attacker, oh_ammo_after)
                attacker.save(update_fields=["conditions"])

    # ---- Gun Fu spend persistence (v0.15.17) -------------------------------
    # Persist the merit-use spend on the underlying Character so the
    # character sheet's existing /spendMeritUse/ count and remaining
    # display reflect the new total immediately. Mirrors the canonical
    # spend pattern from characters/views.py:230 (read merit_uses dict,
    # increment, cap at rating). The cap was already applied via
    # ``min(gun_fu_uses_requested, gun_fu_remaining)`` upstream, so this
    # block trusts ``gun_fu_to_spend`` and never over-counts.
    #
    # The spend lands on the character regardless of per-target outcome
    # (a Gun Fu success that fell on a fully-covered target is still
    # spent — the player committed before resolution, no refund).
    if gun_fu_to_spend > 0 and attacker.character is not None:
        # Defensive re-fetch before mutating the JSONField — earlier
        # housekeeping (willpower / ammo) round-tripped the attacker
        # but the character itself was untouched, so the dict on the
        # in-memory copy is canonical. Still, refresh for symmetry
        # with the encounter's other persistence sites.
        char = attacker.character
        char.refresh_from_db(fields=["merit_uses"])
        uses = dict(char.merit_uses or {})
        uses["Gun Fu"] = int(uses.get("Gun Fu", 0)) + gun_fu_to_spend
        char.merit_uses = uses
        char.save(update_fields=["merit_uses"])
        remaining_after = max(0, gun_fu_remaining - gun_fu_to_spend)
        _log(
            encounter,
            "system",
            f"{attacker.name} spent {gun_fu_to_spend} Gun Fu auto-success(es). "
            f"{remaining_after} remaining this session.",
            actor_participant_id=attacker.id,
            gun_fu_used=gun_fu_to_spend,
            gun_fu_remaining_after=remaining_after,
            gun_fu_rating=gun_fu_rating,
        )

    return redirect("combat:detail", pk=encounter.pk)


# ---------------------------------------------------------------------------
# Conditions, willpower, defensive stances (POST) — v0.15.5
# ---------------------------------------------------------------------------


@login_required
@_gm_or_owner()
@csrf_protect
def set_condition(request, pk, participant_id):
    """POST — append a non-stance condition tag to a participant.

    The ``condition`` form field must be one of the keys in
    ``CONDITION_DEFS`` and must NOT be a stance tag (``defense_full``
    or ``dodging``) — those are set via the dedicated stance buttons
    (``full_defense`` / ``dodge``) which require a roll or auto-math.
    Idempotent: re-submitting an already-set tag is a silent no-op
    (no second log row).

    v0.15.8 — players can self-apply a narrow allow-list of
    conditions on their own character: ``prone`` only. The hard
    incap conditions (``stunned`` / ``blinded`` / ``grappled`` /
    ``incapacitated``) remain GM-imposed; a player POSTing one of
    those gets a flash-message redirect rather than a hard 403 so
    the UI can surface the rejection cleanly.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    encounter = get_object_or_404(Encounter, pk=pk)
    participant = get_object_or_404(
        Participant, pk=participant_id, encounter=encounter
    )

    tag = (request.POST.get("condition", "") or "").strip().lower()
    if tag not in CONDITION_DEFS or tag in _STANCE_TAGS:
        messages.error(request, "Unknown or stance-only condition.")
        return redirect("combat:detail", pk=encounter.pk)

    # v0.15.8 — player self-apply allow-list. Superusers (GM) bypass.
    PLAYER_SELF_APPLY = {"prone"}
    if not request.user.is_superuser and tag not in PLAYER_SELF_APPLY:
        messages.error(
            request,
            f"Players cannot self-apply '{tag}'. Ask the GM.",
        )
        return redirect("combat:detail", pk=encounter.pk)

    conds = list(participant.conditions or [])
    if tag in conds:
        # Idempotent — no log row for re-add.
        return redirect("combat:detail", pk=encounter.pk)

    conds.append(tag)
    participant.conditions = conds
    participant.save(update_fields=["conditions"])

    label = CONDITION_DEFS[tag]["label"]
    _log(
        encounter,
        "condition_set",
        f"{participant.name} gained condition: {label}.",
        target_participant_id=participant.id,
        condition=tag,
    )
    return redirect("combat:detail", pk=encounter.pk)


@login_required
@_gm_or_owner()
@csrf_protect
def clear_condition(request, pk, participant_id):
    """POST — strip a condition tag (and any ``tag:N`` variants).

    The ``condition`` form field can be either a flat tag (e.g.
    ``prone``) or a prefix family (``dodging`` clears
    ``dodging:N`` for any N). Defensive against unknown tags — they
    just no-op rather than 4xx.

    v0.15.8 — players can self-clear a narrow set of tags on their
    own character: ``prone`` (player-applied stance), ``defense_full``
    (their own full-defense), ``dodge_pending`` (their own out-of-turn
    dodge cost), and the ``dodging`` family (their own dodge result).
    GM-imposed conditions (``stunned`` / ``blinded`` / ``grappled``
    / ``incapacitated``) can only be cleared by the GM.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    encounter = get_object_or_404(Encounter, pk=pk)
    participant = get_object_or_404(
        Participant, pk=participant_id, encounter=encounter
    )

    tag = (request.POST.get("condition", "") or "").strip().lower()
    if not tag:
        return redirect("combat:detail", pk=encounter.pk)

    # v0.15.8 — player self-clear allow-list. Superusers (GM) bypass.
    # v0.15.14 — adds ``aiming_at`` so a player can × CANCEL AIM on
    # their own row's banner. The prefix family clause below
    # (``startswith(tag + ":")``) already matches ``aiming_at:<id>:<n>``
    # so a single tag value clears the whole family.
    PLAYER_SELF_CLEAR = {
        "prone", "defense_full", "dodge_pending", "dodging", "aiming_at",
    }
    if not request.user.is_superuser and tag not in PLAYER_SELF_CLEAR:
        messages.error(
            request,
            f"Players cannot self-clear '{tag}'. Ask the GM.",
        )
        return redirect("combat:detail", pk=encounter.pk)

    conds = list(participant.conditions or [])
    before = list(conds)

    # Drop the flat tag, AND any ``tag:N`` family entries.
    conds = [c for c in conds if c != tag and not c.startswith(tag + ":")]

    if conds == before:
        # Tag wasn't present — silent no-op rather than a noisy log row.
        return redirect("combat:detail", pk=encounter.pk)

    participant.conditions = conds
    participant.save(update_fields=["conditions"])

    label = CONDITION_DEFS.get(tag, {}).get("label", tag.upper())
    _log(
        encounter,
        "condition_clear",
        f"{participant.name} cleared condition: {label}.",
        target_participant_id=participant.id,
        condition=tag,
    )
    return redirect("combat:detail", pk=encounter.pk)


@login_required
@_gm_or_owner()
@csrf_protect
def adjust_willpower(request, pk, participant_id):
    """POST — manually set ``willpower_current`` (clamped 0..max).

    Lets the GM edit willpower outside of the attack flow (rest,
    derangements, GM fiat, etc.). The submitted value is clamped to
    ``[0, willpower_max]`` defensively.

    v0.15.8 — players can lower their own willpower (spend it for
    out-of-band purposes) but cannot raise it. Willpower gain is the
    GM's call.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    encounter = get_object_or_404(Encounter, pk=pk)
    participant = get_object_or_404(
        Participant, pk=participant_id, encounter=encounter
    )

    new_value = _safe_int(request.POST.get("willpower_current"), participant.willpower_current)
    new_value = max(0, min(new_value, participant.willpower_max or 0))

    old_value = participant.willpower_current
    if new_value == old_value:
        return redirect("combat:detail", pk=encounter.pk)

    # v0.15.8 — players can only set willpower DOWN. Restoration is
    # GM-only. Soft reject with a flash message rather than a hard 403
    # so the UI surfaces the rule explicitly.
    if not request.user.is_superuser and new_value > old_value:
        messages.error(
            request,
            "Players can only spend willpower, not restore it. Ask the GM.",
        )
        return redirect("combat:detail", pk=encounter.pk)

    participant.willpower_current = new_value
    participant.save(update_fields=["willpower_current"])

    _log(
        encounter,
        "willpower_change",
        f"{participant.name}: WP {old_value} → {new_value}.",
        target_participant_id=participant.id,
        before=old_value,
        after=new_value,
    )
    return redirect("combat:detail", pk=encounter.pk)


@login_required
@_gm_or_owner()
@csrf_protect
def full_defense(request, pk, participant_id):
    """POST — active participant burns their turn for FULL DEFENSE.

    Doubles the participant's defense until the next round. Clears
    automatically at the round boundary in ``next_turn``. Marks the
    participant ``acted_this_round=True`` (eats the turn) but does
    NOT advance the active-participant pointer — the GM clicks NEXT
    TURN to actually pass the turn, same as after an ATTACK.

    v0.15.8 — players may take full defense as their own character
    when it's their turn. The active-turn check below stays in
    place; out-of-turn POSTs are flash-rejected, not 403'd.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    encounter = get_object_or_404(Encounter, pk=pk)
    if encounter.status != "active":
        messages.error(request, "Cannot stance outside an active encounter.")
        return redirect("combat:detail", pk=encounter.pk)

    participant = get_object_or_404(
        Participant, pk=participant_id, encounter=encounter
    )

    if encounter.active_participant_id != participant.id:
        messages.error(request, "Full defense must be taken on your own turn.")
        return redirect("combat:detail", pk=encounter.pk)

    # v0.15.14 — defending breaks aim. Compute whether we had aim
    # before the strip so we can log a clarifying message.
    had_aim = _aim_state(participant) is not None

    conds = list(participant.conditions or [])
    if "defense_full" not in conds:
        conds.append("defense_full")
    participant.conditions = conds
    if had_aim:
        _strip_aim(participant)
    participant.acted_this_round = True
    participant.save(update_fields=["conditions", "acted_this_round"])

    _log(
        encounter,
        "full_defense",
        f"{participant.name} takes full defense — defense doubled until next round.",
        actor_participant_id=participant.id,
    )
    if had_aim:
        _log(
            encounter,
            "system",
            f"{participant.name}'s aim broken — took full defense.",
            actor_participant_id=participant.id,
        )
    return redirect("combat:detail", pk=encounter.pk)


@login_required
@_gm_or_owner()
@csrf_protect
def reload_weapon(request, pk, participant_id):
    """POST — reload the participant's equipped firearm to a full magazine.

    v0.15.15 — players have unlimited magazines (no reserve tracking),
    so reload is always available. The action resets the ammo tag to
    the catalogue ``magazine`` value.

    Turn cost mirrors the ``full_defense`` / ``dodge`` / ``aim``
    pattern: when called by the **active** participant, the action
    consumes the turn (``acted_this_round=True``) but does NOT
    auto-advance the pointer — the GM clicks NEXT TURN to actually
    pass the turn. When called off-turn (typically a GM bookkeeping
    nicety between rounds), no turn is consumed; an extra ``system``
    log row notes the out-of-band reload so the timeline reads
    accurately.

    Rejected (flash + redirect) when:
    * encounter is not active
    * the participant has no equipped weapon, or has a non-firearm
      equipped, or has a firearm with no ``magazine`` size on file
      (legacy / hand-edited catalogue entry)

    Note on naming: the URL is bound as ``combat:reload`` so callers
    can use the natural verb. The Python view is named
    ``reload_weapon`` to avoid shadowing the ``reload`` builtin at
    module scope.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    encounter = get_object_or_404(Encounter, pk=pk)
    if encounter.status != "active":
        messages.error(request, "Cannot reload outside an active encounter.")
        return redirect("combat:detail", pk=encounter.pk)

    participant = get_object_or_404(
        Participant, pk=participant_id, encounter=encounter
    )

    weapon_data = participant.weapon_data or {}
    if weapon_data.get("category") != "firearm":
        messages.error(
            request, "Cannot reload: equipped weapon is not a firearm."
        )
        return redirect("combat:detail", pk=encounter.pk)

    try:
        mag_size = int(weapon_data.get("magazine", 0) or 0)
    except (TypeError, ValueError):
        mag_size = 0
    if mag_size <= 0:
        messages.error(
            request,
            "Cannot reload: equipped weapon has no magazine size on file.",
        )
        return redirect("combat:detail", pk=encounter.pk)

    on_turn = (encounter.active_participant_id == participant.id)

    _set_ammo(participant, mag_size)
    if on_turn:
        participant.acted_this_round = True
        participant.save(update_fields=["conditions", "acted_this_round"])
    else:
        participant.save(update_fields=["conditions"])

    _log(
        encounter,
        "reload",
        f"{participant.name} reloaded — {mag_size} rounds chambered.",
        actor_participant_id=participant.id,
        weapon_name=participant.weapon_name,
        magazine=mag_size,
        mag_size=mag_size,
        on_turn=on_turn,
    )
    if not on_turn:
        # Off-turn reload — flag so the timeline reads accurately.
        # The GM can still see who reloaded between rounds without
        # confusing it for an in-turn action.
        _log(
            encounter,
            "system",
            f"{participant.name}: out-of-band reload (off-turn — no turn consumed).",
            actor_participant_id=participant.id,
        )
    return redirect("combat:detail", pk=encounter.pk)


@login_required
@_gm_or_owner()
@csrf_protect
def dodge(request, pk, participant_id):
    """POST — roll a dodge pool and store it as a ``dodging:N`` tag.

    Pool: ``Dex + Athletics`` for character / NPC, ``mook_defense``
    for mooks. The rolled successes replace the participant's normal
    defense via the ``dodging`` branch of ``_compute_defense``.

    Turn cost:

    * If the dodger is the **active** participant → eats this turn
      (``acted_this_round=True``).
    * Otherwise → eats their **next** turn. We tag ``dodge_pending``
      so ``next_turn`` can mark them acted as soon as their turn
      starts (and then immediately clear ``dodge_pending``).

    Strips any prior ``dodging:*`` tags before appending so re-rolls
    don't leave dead state behind.

    v0.15.8 — players may dodge on their own character row at any
    time (in or out of turn) per WoD 2.0 rules.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    encounter = get_object_or_404(Encounter, pk=pk)
    if encounter.status != "active":
        messages.error(request, "Cannot dodge outside an active encounter.")
        return redirect("combat:detail", pk=encounter.pk)

    participant = get_object_or_404(
        Participant, pk=participant_id, encounter=encounter
    )

    # Compose the dodge pool. Same defensive try/except shape as
    # _baseline_defense — partial sheets fall back to 0 rather than
    # crashing the request.
    if participant.participant_kind == "mook":
        pool = participant.mook_defense or 0
    else:
        source = participant.character or participant.npc
        if source is None:
            pool = 0
        else:
            try:
                dex = int(source.attributes["finesse"]["physical"])
                athletics = int(source.skills["physical"].get("Athletics", 0))
                pool = dex + athletics
            except (KeyError, TypeError, ValueError):
                pool = 0

    # Wound + condition mods apply to dodge too — it's a dice pool.
    pool = pool + _wound_penalty(participant) + _condition_attack_modifier(participant)
    pool = max(0, pool)

    successes, dice = _roll_pool(pool)

    # v0.15.14 — dodging breaks aim. Detect before we rebuild the
    # conditions list so we can log a clarifying system row when the
    # dodger had been aiming.
    had_aim = _aim_state(participant) is not None

    # Strip any prior dodge tag, then append the fresh one.
    conds = _strip_prefix_conditions(list(participant.conditions or []), "dodging")
    # v0.15.14 — also strip any aiming_at:* tag from this fresh
    # conditions list before persisting (mirrors the dodge-tag strip).
    conds = [c for c in conds if not c.startswith("aiming_at:")]

    is_active = (encounter.active_participant_id == participant.id)
    update_fields = ["conditions"]

    if is_active:
        participant.acted_this_round = True
        update_fields.append("acted_this_round")
        cost_label = "this turn"
    else:
        # Out-of-turn dodge — pay it next turn instead.
        if "dodge_pending" not in conds:
            conds.append("dodge_pending")
        cost_label = "next turn"

    conds.append(f"dodging:{successes}")
    participant.conditions = conds
    participant.save(update_fields=update_fields)

    _log(
        encounter,
        "dodge",
        f"{participant.name} dodges — {pool}d → {successes} successes "
        f"(costs {cost_label}).",
        actor_participant_id=participant.id,
        pool=pool,
        dice=dice,
        successes=successes,
        is_active_turn=is_active,
    )
    if had_aim:
        _log(
            encounter,
            "system",
            f"{participant.name}'s aim broken — dodged.",
            actor_participant_id=participant.id,
        )
    return redirect("combat:detail", pk=encounter.pk)


# ---------------------------------------------------------------------------
# v0.15.7 — REST/JSON API for the MCP server
# ---------------------------------------------------------------------------
#
# These endpoints are reached via the MCP token middleware
# (``exodus.mcp_auth.MCPTokenAuthMiddleware``): a request carrying a
# valid ``Authorization: Bearer <token>`` header is authenticated as
# the first active superuser and has CSRF disabled. Session-cookie
# superusers can also reach these endpoints directly (admin debugging).
#
# Anyone else gets a JSON 403, NOT the HTML clearance-gate response —
# clients are expected to be machines.
#
# Lifecycle / participants are exposed deliberately. **Attack, dodge,
# stance, condition, and willpower mutations are intentionally NOT
# exposed** — those stay behind the GM's keyboard in the web UI
# where errors are visible and recoverable.


def _api_gm_only(view):
    """Decorator: 403 JSON unless the caller is a superuser.

    Mirrors ``_gm_only`` but returns JSON so the MCP client can
    surface the rejection cleanly. The MCPTokenAuthMiddleware swaps
    in a superuser when the bearer token is valid, so the only
    callers that hit the 403 branch are anonymous / non-superuser
    sessions.
    """
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required."}, status=401)
        if not request.user.is_superuser:
            return JsonResponse({"error": "ACCESS DENIED."}, status=403)
        return view(request, *args, **kwargs)
    wrapped.__name__ = view.__name__
    wrapped.__doc__ = view.__doc__
    return wrapped


def _serialize_log_entry(entry):
    """Render a CombatLog row as a JSON-safe dict.

    Used by the detail endpoint and log-fetch helpers. ``data`` is
    already a JSONField so it round-trips cleanly. Timestamps are
    ISO-formatted for portability.
    """
    return {
        "id": entry.id,
        "sequence": entry.sequence,
        "round_number": entry.round_number,
        "action_type": entry.action_type,
        "message": entry.message,
        "data": entry.data or {},
        "actor_participant_id": entry.actor_participant_id,
        "target_participant_id": entry.target_participant_id,
        "is_reverted": entry.is_reverted,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }


def _serialize_participant(p):
    """Render a Participant as a JSON-safe dict — full snapshot.

    Includes the denormalised actor name, FK ids, faction, kind,
    health track, willpower, cover state, weapon / armor names,
    conditions list, and initiative state. The MCP client uses this
    directly so the GM-side LLM can reason about the live encounter
    state without a second round-trip.
    """
    return {
        "id": p.id,
        "encounter_id": p.encounter_id,
        "participant_kind": p.participant_kind,
        "character_id": p.character_id,
        "npc_id": p.npc_id,
        "name": p.name,
        "faction": p.faction,
        "initiative_score": p.initiative_score,
        "initiative_roll": p.initiative_roll,
        "health": {
            "bashing": p.health_bashing,
            "lethal": p.health_lethal,
            "aggravated": p.health_aggravated,
            "max": p.health_max,
        },
        "willpower": {
            "current": p.willpower_current,
            "max": p.willpower_max,
        },
        "mental_load": p.mental_load,
        "cover": {
            "state": p.cover_state,
            "entry_name": p.cover_entry_name,
            "durability": p.cover_durability,
            "health": p.cover_health,
        },
        "weapon": {
            "name": p.weapon_name,
            "data": p.weapon_data or {},
        },
        "armor": {
            "name": p.armor_name,
            "data": p.armor_data or {},
        },
        "conditions": list(p.conditions or []),
        "position_label": p.position_label,
        "position_order": p.position_order,
        "mook_combat_pool": p.mook_combat_pool,
        "mook_defense": p.mook_defense,
        "mook_armor_rating": p.mook_armor_rating,
        "surprise_immune": p.surprise_immune,
        "acted_this_round": p.acted_this_round,
        "defense_override": p.defense_override,
        "notes": p.notes,
    }


def _serialize_encounter(enc, with_log=False, log_limit=50):
    """Render an Encounter as a JSON-safe dict.

    ``with_log=False`` keeps the payload list-friendly (just the
    encounter shell). ``with_log=True`` includes the participant
    list and the most-recent ``log_limit`` log entries (newest
    first), which is what the detail endpoint serves.
    """
    out = {
        "id": enc.id,
        "title": enc.title,
        "status": enc.status,
        "round_number": enc.round_number,
        "active_participant_id": enc.active_participant_id,
        "initiative_order": list(enc.initiative_order or []),
        "scene_description": enc.scene_description,
        "location_text": enc.location_text,
        "started_at": enc.started_at.isoformat() if enc.started_at else None,
        "ended_at": enc.ended_at.isoformat() if enc.ended_at else None,
        "created_at": enc.created_at.isoformat() if enc.created_at else None,
        "updated_at": enc.updated_at.isoformat() if enc.updated_at else None,
        "gm_username": enc.gm.username if enc.gm_id else None,
        "story_idea_id": enc.story_idea_id,
        "story_idea_title": enc.story_idea.title if enc.story_idea_id else None,
        "participant_count": enc.participants.count(),
    }
    if with_log:
        out["participants"] = [
            _serialize_participant(p)
            for p in enc.participants.all().order_by("position_order", "id")
        ]
        # Last N entries newest-first; the GM's LLM usually wants the
        # most recent context, not the whole log of a 30-round fight.
        recent = list(
            enc.log_entries.order_by("-sequence")[:max(0, int(log_limit))]
        )
        out["log_entries"] = [_serialize_log_entry(e) for e in recent]
        out["log_entries_returned"] = len(recent)
    return out


@csrf_exempt
@require_http_methods(["GET", "POST"])
@login_required
@_api_gm_only
def api_encounters(request):
    """GET — list every encounter (newest first). POST — create one.

    POST body (JSON or form): ``title``, ``scene_description``,
    ``location_text``, ``story_idea_id`` (optional). Mirrors the form
    surface in ``encounter_create`` so the MCP tool can hand off the
    same payload the web form would.
    """
    if request.method == "GET":
        encounters = Encounter.objects.all().order_by("-created_at")
        return JsonResponse({
            "count": encounters.count(),
            "encounters": [_serialize_encounter(e) for e in encounters],
        })

    # POST — create
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    title = (body.get("title") or "").strip() or "Untitled Encounter"
    encounter = Encounter.objects.create(
        title=title[:200],
        scene_description=(body.get("scene_description") or "").strip(),
        location_text=(body.get("location_text") or "").strip()[:200],
        gm=request.user,
        status="setup",
        round_number=0,
        story_idea=_resolve_story_idea(body.get("story_idea_id")),
    )
    _log(encounter, "system", "Encounter created.")
    return JsonResponse(_serialize_encounter(encounter, with_log=True), status=201)


@csrf_exempt
@require_http_methods(["GET"])
@login_required
@_api_gm_only
def api_encounter_detail(request, pk):
    """GET — single encounter with participants + recent log.

    Querystring ``log_limit`` (default 50, max 500) bounds how many
    of the most-recent log entries are inlined. Larger windows are
    rejected so the MCP client can't accidentally pull a 50,000-row
    timeline through the wire.
    """
    try:
        log_limit = int(request.GET.get("log_limit", 50))
    except (TypeError, ValueError):
        log_limit = 50
    log_limit = max(0, min(500, log_limit))

    encounter = get_object_or_404(Encounter, pk=pk)
    return JsonResponse(_serialize_encounter(
        encounter, with_log=True, log_limit=log_limit,
    ))


@csrf_exempt
@require_http_methods(["POST"])
@login_required
@_api_gm_only
def api_encounter_lifecycle(request, pk):
    """POST — drive setup → active → concluded transitions.

    Body: ``{"action": "start" | "end"}``. ``start`` mirrors
    ``start_encounter`` (gates on every participant having rolled,
    rebuilds order, stamps ``started_at``); ``end`` mirrors
    ``end_encounter``. Idempotent-ish: re-calling ``start`` on an
    already-active encounter or ``end`` on an already-concluded one
    returns 409 rather than silently no-op'ing, so the MCP caller
    can detect state drift.
    """
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    action = (body.get("action") or "").strip().lower()
    encounter = get_object_or_404(Encounter, pk=pk)

    if action == "start":
        if encounter.status != "setup":
            return JsonResponse({
                "error": f"Cannot start: encounter is {encounter.status}.",
            }, status=409)
        unrolled = encounter.participants.filter(
            initiative_score__isnull=True
        ).count()
        if unrolled > 0:
            return JsonResponse({
                "error": f"{unrolled} participants have not rolled initiative yet.",
            }, status=409)
        ordered = list(encounter.participants.order_by("-initiative_score", "id"))
        if not ordered:
            return JsonResponse({
                "error": "Cannot start an encounter with no participants.",
            }, status=409)
        encounter.initiative_order = [p.id for p in ordered]
        encounter.active_participant_id = ordered[0].id
        encounter.status = "active"
        encounter.round_number = 1
        encounter.started_at = timezone.now()
        encounter.save(update_fields=[
            "initiative_order", "active_participant_id", "status",
            "round_number", "started_at", "updated_at",
        ])
        encounter.participants.update(acted_this_round=False)
        _log(
            encounter, "system",
            f"Encounter started — round 1, {ordered[0].name} acts first.",
            first_participant_id=ordered[0].id,
        )
        return JsonResponse(_serialize_encounter(encounter, with_log=True))

    if action == "end":
        if encounter.status == "concluded":
            return JsonResponse({
                "error": "Encounter already concluded.",
            }, status=409)
        rounds = encounter.round_number
        encounter.status = "concluded"
        encounter.active_participant_id = None
        encounter.ended_at = timezone.now()
        encounter.save(update_fields=[
            "status", "active_participant_id", "ended_at", "updated_at",
        ])
        _log(
            encounter, "system",
            f"Encounter concluded after {rounds} round(s).",
            rounds=rounds,
        )
        return JsonResponse(_serialize_encounter(encounter, with_log=True))

    return JsonResponse({
        "error": "Unknown action. Use 'start' or 'end'.",
    }, status=400)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
@_api_gm_only
def api_encounter_initiative(request, pk):
    """POST — roll initiative for every unrolled participant.

    Mirror of ``roll_initiative_all`` — same per-roll log row, same
    rebuilt ``initiative_order``, same summary system row. No body.
    Refuses to act on a concluded encounter (409).
    """
    encounter = get_object_or_404(Encounter, pk=pk)
    if encounter.status == "concluded":
        return JsonResponse({
            "error": "Cannot roll initiative on a concluded encounter.",
        }, status=409)

    unrolled = list(
        encounter.participants.filter(initiative_score__isnull=True).order_by("id")
    )
    rolled = []
    for participant in unrolled:
        modifier, d10, score = _compute_initiative(participant)
        participant.initiative_roll = d10
        participant.initiative_score = score
        participant.save(update_fields=["initiative_roll", "initiative_score"])
        _log(
            encounter, "initiative",
            f"{participant.name} rolled initiative: {modifier} + {d10} = {score}.",
            participant_id=participant.pk,
            modifier=modifier, d10=d10, score=score,
        )
        rolled.append({
            "participant_id": participant.id,
            "name": participant.name,
            "modifier": modifier,
            "d10": d10,
            "score": score,
        })

    encounter.initiative_order = [
        p.id
        for p in encounter.participants.exclude(
            initiative_score__isnull=True
        ).order_by("-initiative_score", "id")
    ]
    encounter.save(update_fields=["initiative_order", "updated_at"])
    _log(
        encounter, "system",
        f"Initiative rolled for {len(rolled)} participants.",
        count=len(rolled),
    )
    return JsonResponse({
        "rolled_count": len(rolled),
        "rolls": rolled,
        "encounter": _serialize_encounter(encounter, with_log=True),
    })


@csrf_exempt
@require_http_methods(["POST"])
@login_required
@_api_gm_only
def api_encounter_turn(request, pk):
    """POST — advance to the next turn (or roll the round over).

    Mirror of ``next_turn``. Rejects on non-active encounters with a
    409 so the MCP client gets a structured error rather than a no-op
    redirect.
    """
    encounter = get_object_or_404(Encounter, pk=pk)
    if encounter.status != "active":
        return JsonResponse({
            "error": f"Cannot advance turn: encounter is {encounter.status}.",
        }, status=409)

    order = list(encounter.initiative_order or [])
    if not order:
        return JsonResponse({
            "error": "Encounter has no initiative order.",
        }, status=409)

    current_id = encounter.active_participant_id
    if current_id is not None:
        Participant.objects.filter(pk=current_id, encounter=encounter).update(
            acted_this_round=True
        )

    try:
        idx = order.index(current_id)
    except ValueError:
        idx = -1

    rolled_round = False
    if idx >= len(order) - 1:
        # End of round — roll over.
        encounter.round_number += 1
        encounter.participants.update(acted_this_round=False)
        cleared_any = False
        for p in encounter.participants.all():
            new_conds = [
                c for c in (p.conditions or [])
                if c != "defense_full" and not c.startswith("dodging:")
            ]
            if new_conds != (p.conditions or []):
                p.conditions = new_conds
                p.save(update_fields=["conditions"])
                cleared_any = True
        next_id = order[0]
        encounter.active_participant_id = next_id
        encounter.save(update_fields=[
            "round_number", "active_participant_id", "updated_at",
        ])
        _log(
            encounter, "round_advance",
            f"Round {encounter.round_number} begins.",
            round_number=encounter.round_number,
        )
        if cleared_any:
            _log(encounter, "system", "Defensive stances cleared at round boundary.")
        rolled_round = True
    else:
        next_id = order[idx + 1]
        encounter.active_participant_id = next_id
        encounter.save(update_fields=["active_participant_id", "updated_at"])
        next_p = encounter.participants.filter(pk=next_id).first()
        next_name = next_p.name if next_p else f"#{next_id}"
        _log(
            encounter, "turn_advance",
            f"Turn passes to {next_name}.",
            participant_id=next_id,
        )

    # Out-of-turn dodge cost (matches next_turn).
    new_active = encounter.participants.filter(
        pk=encounter.active_participant_id
    ).first()
    if new_active is not None and "dodge_pending" in (new_active.conditions or []):
        new_active.conditions = [
            c for c in (new_active.conditions or []) if c != "dodge_pending"
        ]
        new_active.acted_this_round = True
        new_active.save(update_fields=["conditions", "acted_this_round"])
        _log(
            encounter, "system",
            f"{new_active.name}: dodge_pending consumed — turn skipped.",
            target_participant_id=new_active.id,
        )

    return JsonResponse({
        "rolled_round": rolled_round,
        "encounter": _serialize_encounter(encounter, with_log=True),
    })


@csrf_exempt
@require_http_methods(["POST"])
@login_required
@_api_gm_only
def api_encounter_participants(request, pk):
    """POST — add a participant to an encounter.

    Body: ``{"kind": "character"|"npc"|"template", ...}`` plus the
    matching id field (``character_id`` / ``npc_id`` / ``template_name``)
    and an optional ``faction`` (defaults vary by kind, matching the
    web form's defaults). Mirrors ``participant_add``'s spawn logic
    so denormalisation stays consistent.
    """
    encounter = get_object_or_404(Encounter, pk=pk)

    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    kind = (body.get("kind") or "").strip().lower()
    if kind not in ("character", "npc", "template"):
        return JsonResponse({
            "error": "kind must be one of: character, npc, template.",
        }, status=400)

    next_pos = (
        encounter.participants.aggregate(Max("position_order"))["position_order__max"] or 0
    ) + 1

    participant = None

    if kind == "character":
        character_id = body.get("character_id")
        if not character_id:
            return JsonResponse({"error": "character_id is required."}, status=400)
        character = Character.objects.filter(pk=character_id).first()
        if character is None:
            return JsonResponse({"error": "Character not found."}, status=404)
        try:
            stamina = int(character.attributes["resistance"]["physical"])
            health_max = int(character.size) + stamina
        except (KeyError, TypeError, ValueError):
            health_max = 7
        try:
            willpower_max = int(character.attributes["resistance"]["mental"]) + int(
                character.attributes["resistance"]["social"]
            )
        except (KeyError, TypeError, ValueError):
            willpower_max = 0
        faction = (body.get("faction") or "player").strip().lower()
        # v0.15.12 — API path mirrors the web form's join-time copy so MCP /
        # external callers also snapshot the canonical sheet's current state.
        participant = Participant.objects.create(
            encounter=encounter,
            participant_kind="character",
            character=character,
            name=character.name,
            faction=faction,
            health_max=health_max,
            health_bashing=character.health_bashing,
            health_lethal=character.health_lethal,
            health_aggravated=character.health_aggravated,
            willpower_max=willpower_max,
            willpower_current=character.willpower_current,
            mental_load=getattr(character, "mental_load", 0),
            position_order=next_pos,
        )

    elif kind == "npc":
        npc_id = body.get("npc_id")
        if not npc_id:
            return JsonResponse({"error": "npc_id is required."}, status=400)
        npc_obj = NPC.objects.filter(pk=npc_id).first()
        if npc_obj is None:
            return JsonResponse({"error": "NPC not found."}, status=404)
        try:
            stamina = int(npc_obj.attributes["resistance"]["physical"])
            health_max = int(npc_obj.size) + stamina
        except (KeyError, TypeError, ValueError):
            health_max = 7
        try:
            willpower_max = int(npc_obj.attributes["resistance"]["mental"]) + int(
                npc_obj.attributes["resistance"]["social"]
            )
        except (KeyError, TypeError, ValueError):
            willpower_max = 0
        faction = (body.get("faction") or "hostile").strip().lower()
        # v0.15.12 — same canonical-state copy on the NPC API branch.
        participant = Participant.objects.create(
            encounter=encounter,
            participant_kind="npc",
            npc=npc_obj,
            name=npc_obj.name,
            faction=faction,
            health_max=health_max,
            health_bashing=npc_obj.health_bashing,
            health_lethal=npc_obj.health_lethal,
            health_aggravated=npc_obj.health_aggravated,
            willpower_max=willpower_max,
            willpower_current=npc_obj.willpower_current,
            mental_load=getattr(npc_obj, "mental_load", 0),
            position_order=next_pos,
        )

    elif kind == "template":
        template_name = (body.get("template_name") or "").strip()
        if not template_name:
            return JsonResponse({"error": "template_name is required."}, status=400)
        templates = SiteSettings.load().get_combat_npcs()
        entry = next((t for t in templates if t.get("name") == template_name), None)
        if entry is None:
            return JsonResponse({
                "error": f"Combat NPC template '{template_name}' not found.",
            }, status=404)
        faction = (body.get("faction") or "hostile").strip().lower()
        participant = Participant.objects.create(
            encounter=encounter,
            participant_kind="mook",
            name=entry.get("name", "Mook"),
            faction=faction,
            mook_combat_pool=_safe_int(entry.get("combat_pool"), 0),
            mook_defense=_safe_int(entry.get("defense"), 0),
            health_max=_safe_int(entry.get("health_max"), 7),
            mook_armor_rating=entry.get("armor_rating", "") or "",
            weapon_name=entry.get("weapon", "") or "",
            notes=entry.get("notes", "") or "",
            position_order=next_pos,
        )

    if participant is not None:
        # v0.15.12 — same join-time health surfacing as the web form.
        health_at_join = {
            "bashing": participant.health_bashing,
            "lethal": participant.health_lethal,
            "aggravated": participant.health_aggravated,
            "willpower_current": participant.willpower_current,
            "willpower_max": participant.willpower_max,
        }
        _log(
            encounter, "system",
            f"Added {participant.name} ({participant.faction}) to encounter.",
            participant_id=participant.pk,
            participant_kind=participant.participant_kind,
            faction=participant.faction,
            health_at_join=health_at_join,
        )
        return JsonResponse(_serialize_participant(participant), status=201)

    return JsonResponse({"error": "Failed to add participant."}, status=400)


@csrf_exempt
@require_http_methods(["DELETE"])
@login_required
@_api_gm_only
def api_encounter_participant_detail(request, pk, participant_id):
    """DELETE — remove a participant from an encounter.

    Returns the captured display name so the MCP client gets a
    confirmation payload it can show back to the GM. CASCADE handles
    log row repointing (target_participant / actor_participant are
    SET_NULL on the FK).
    """
    encounter = get_object_or_404(Encounter, pk=pk)
    participant = get_object_or_404(
        Participant, pk=participant_id, encounter=encounter
    )
    name = participant.name
    captured_id = participant.id
    participant.delete()
    _log(
        encounter, "system",
        f"Removed {name} from encounter.",
        participant_id=captured_id,
    )
    return JsonResponse({
        "deleted": True,
        "participant_id": captured_id,
        "name": name,
    })
