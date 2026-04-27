"""Views for the personal combat app.

v0.15.2 — encounter CRUD. GM-only list and detail pages plus six
POST endpoints for creating / updating / deleting encounters and
adding / removing participants.

Three participant kinds are supported:

* ``character`` — links to a player :class:`characters.Character`.
* ``npc``       — links to an :class:`npcs.NPC` dossier (filtered to
                  full NPCs, not GM dossiers).
* ``mook``      — snapshot from the
                  :class:`exodus.SiteSettings` ``combat_npcs``
                  catalogue. Catalogue entries are denormalised at
                  spawn so later catalogue edits do not mutate
                  in-flight encounters.

No rolls, no initiative, no real-time fan-out yet — those land in
v0.15.3+. The CombatLog timeline is read-only here and uses
``action_type='system'`` for every entry written by these views.
"""

from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.http import HttpResponseForbidden, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
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
