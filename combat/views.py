"""Views for the personal combat app.

v0.15.3 — initiative + turn advance. Builds on the encounter CRUD
shipped in v0.15.2 with WoD 2.0 initiative rolls (per-participant,
roll-all, clear) and the encounter lifecycle transitions
``setup → active → concluded`` driven by START / NEXT TURN / END
endpoints.

Initiative model:

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

The CombatLog timeline now distinguishes action types:
``initiative``, ``turn_advance``, ``round_advance``, ``system``.
Real-time fan-out (WebSocket broadcast) lands in v0.15.6.
"""

import secrets

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import F, Max
from django.http import HttpResponseForbidden, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect

from characters.models import Character
from exodus.models import SiteSettings
from npcs.models import NPC

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
    """Append a single CombatLog row.

    Keyword arguments are stuffed into the ``data`` JSONField so callers
    can attach arbitrary structured payloads (e.g. a participant id or
    a faction tag) without touching the schema.
    """
    return CombatLog.objects.create(
        encounter=encounter,
        sequence=_next_sequence(encounter),
        round_number=encounter.round_number,
        action_type=action_type,
        message=message,
        data=data,
    )


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


# ---------------------------------------------------------------------------
# Page views
# ---------------------------------------------------------------------------


@login_required
@_gm_only
def encounter_list_page(request):
    """GET — render the encounter directory.

    Each row exposes a participant count (computed at the queryset
    level via ``prefetch_related``) and a status badge. Empty list
    is allowed and rendered with a placeholder.
    """
    encounters = Encounter.objects.all().prefetch_related("participants")
    enriched = []
    for enc in encounters:
        # Cache the participant count on the object so the template
        # can read it without retriggering the query.
        enc.participant_count = enc.participants.count()
        enriched.append(enc)
    return render(
        request,
        "combat/list.html",
        {"encounters": enriched},
    )


@login_required
@_gm_only
def encounter_page(request, pk):
    """GET — render a single encounter with its participants and log.

    Spawn sources are passed in directly as querysets / lists; the
    template iterates them inside the "+ ADD PARTICIPANT" panel.
    """
    encounter = get_object_or_404(Encounter, pk=pk)

    # Participants split by faction so the three columns can each
    # iterate their own slice without re-filtering in the template.
    participants = list(encounter.participants.all().order_by("position_order", "id"))
    by_faction = {
        "player_or_ally": [p for p in participants if p.faction in ("player", "ally")],
        "hostile": [p for p in participants if p.faction == "hostile"],
        "neutral": [p for p in participants if p.faction == "neutral"],
    }

    # Initiative tracker: ordered by score descending with id as the
    # deterministic tiebreak, nulls last so unrolled participants sink
    # to the bottom of the tracker.
    ordered_participants = list(
        encounter.participants.order_by(
            F("initiative_score").desc(nulls_last=True), "id"
        )
    )

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
    available_npcs = NPC.objects.filter(is_npc_dossier=False).order_by("name")
    combat_npc_templates = SiteSettings.load().get_combat_npcs()

    # Group templates by category for the optgroup layout.
    combat_npcs_by_cat = {}
    for entry in combat_npc_templates:
        cat = entry.get("category", "other") or "other"
        combat_npcs_by_cat.setdefault(cat, []).append(entry)

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
            "combat_npc_templates": combat_npc_templates,
            "combat_npcs_by_cat": combat_npcs_by_cat,
        },
    )


# ---------------------------------------------------------------------------
# Encounter CRUD (POST)
# ---------------------------------------------------------------------------


@login_required
@_gm_only
@csrf_protect
def encounter_create(request):
    """POST — create a new encounter and seed its log with a system row."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    encounter = Encounter.objects.create(
        title=request.POST.get("title", "").strip() or "Untitled Encounter",
        scene_description=request.POST.get("scene_description", "").strip(),
        location_text=request.POST.get("location_text", "").strip(),
        gm=request.user,
        status="setup",
        round_number=0,
    )
    # First log row is always sequence=1; seed via the helper so the
    # invariant holds even if a future migration backfills history.
    _log(encounter, "system", "Encounter created.")
    return redirect("combat:detail", pk=encounter.pk)


@login_required
@_gm_only
@csrf_protect
def encounter_update(request, pk):
    """POST — update an encounter's metadata (title / scene / location)."""
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
    encounter.save(update_fields=["title", "scene_description", "location_text", "updated_at"])

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
        participant = Participant.objects.create(
            encounter=encounter,
            participant_kind="character",
            character=character,
            name=character.name,
            faction=faction,
            health_max=health_max,
            willpower_max=willpower_max,
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
        participant = Participant.objects.create(
            encounter=encounter,
            participant_kind="npc",
            npc=npc_obj,
            name=npc_obj.name,
            faction=faction,
            health_max=health_max,
            willpower_max=willpower_max,
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
        _log(
            encounter,
            "system",
            f"Added {participant.name} ({participant.faction}) to encounter.",
            participant_id=participant.pk,
            participant_kind=participant.participant_kind,
            faction=participant.faction,
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
@_gm_only
@csrf_protect
def roll_initiative(request, pk, participant_id):
    """POST — roll initiative for a single participant.

    Rejected as a no-op redirect when the encounter is already
    concluded (rolls into a closed encounter make no game sense and
    would corrupt the timeline).
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

    _log(
        encounter,
        "system",
        f"Encounter started — round 1, {ordered[0].name} acts first.",
        first_participant_id=ordered[0].id,
    )
    return redirect("combat:detail", pk=encounter.pk)


@login_required
@_gm_only
@csrf_protect
def next_turn(request, pk):
    """POST — advance the active participant pointer.

    If the current participant is the last in ``initiative_order`` the
    round rolls over: ``round_number`` increments, every participant's
    ``acted_this_round`` flag is reset, and the pointer wraps to the
    top of the order (logged as ``round_advance``). Otherwise the
    pointer steps forward one slot and a ``turn_advance`` row is
    written.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    encounter = get_object_or_404(Encounter, pk=pk)
    if encounter.status != "active":
        return redirect("combat:detail", pk=encounter.pk)

    order = list(encounter.initiative_order or [])
    if not order:
        # Defensive: an active encounter with no order is malformed,
        # but bail rather than crash so the GM can recover with CLEAR.
        return redirect("combat:detail", pk=encounter.pk)

    # Mark the current actor as acted, then look up the next slot.
    current_id = encounter.active_participant_id
    if current_id is not None:
        Participant.objects.filter(pk=current_id, encounter=encounter).update(
            acted_this_round=True
        )

    try:
        idx = order.index(current_id)
    except ValueError:
        # Active pointer not in order (e.g. the active participant was
        # removed). Fall back to slot 0.
        idx = -1

    if idx >= len(order) - 1:
        # End of round — roll over.
        encounter.round_number += 1
        encounter.participants.update(acted_this_round=False)
        next_id = order[0]
        encounter.active_participant_id = next_id
        encounter.save(
            update_fields=[
                "round_number",
                "active_participant_id",
                "updated_at",
            ]
        )
        _log(
            encounter,
            "round_advance",
            f"Round {encounter.round_number} begins.",
            round_number=encounter.round_number,
        )
    else:
        next_id = order[idx + 1]
        encounter.active_participant_id = next_id
        encounter.save(update_fields=["active_participant_id", "updated_at"])
        # Resolve the next participant's name for the log message —
        # may be missing if a delete just SET_NULL'd them.
        next_p = encounter.participants.filter(pk=next_id).first()
        next_name = next_p.name if next_p else f"#{next_id}"
        _log(
            encounter,
            "turn_advance",
            f"Turn passes to {next_name}.",
            participant_id=next_id,
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

    _log(
        encounter,
        "system",
        f"Encounter concluded after {rounds} round(s).",
        rounds=rounds,
    )
    return redirect("combat:list")
