"""Views for the personal combat app.

v0.15.4 — attack actions + damage. Layers a server-rolled WoD 2.0
attack pipeline on top of the v0.15.3 initiative + turn loop, plus
**equip-weapon / equip-armor / set-cover** endpoints that snapshot
catalogue entries onto the active participant.

Attack pipeline:

1. Compose the attacker's pool —
   ``Dexterity + chosen weapon skill + weapon dice modifier + GM
   modifier`` for character / NPC, or ``mook_combat_pool + GM
   modifier`` for mooks.
2. Compute the target's defense — ``min(Dex, Wits) + Athletics`` for
   character / NPC, ``mook_defense`` for mooks. ``defense_override``
   wins if set.
3. Apply cover — ``light=-2``, ``heavy=-4``, ``full`` blocks the
   shot entirely (logged ``outcome="blocked_by_cover"``).
4. Floor the dice pool at ``0`` and roll — ``_roll_pool`` reuses the
   ``secrets`` source from initiative; 8/9/10 are successes, 10s
   "explode" and re-roll up to five recursion levels deep so the
   pathological all-tens case can't run away.
5. On any successes, compute damage — ``successes + weapon damage``,
   minus armor (``B`` track or ``L`` track from ``"B/L"`` rating;
   aggravated bypasses armor). Apply to the matching health track,
   capped at ``health_max``; overflow is logged but no track-upgrade
   (bashing→lethal→aggravated) is enforced yet — that lands in
   v0.15.5.
6. Append two log rows on a hit: ``attack`` (the resolution payload)
   and ``health_change`` (so the timeline can be filtered down to
   damage-only events). Misses write a single ``attack`` row.

This release is **GM-only** — the player-facing surface lands in
v0.15.6 with the WebSocket fan-out. Faction is decorative; the
target picker offers every other participant in the encounter so
PvP works out of the box.

Initiative model (v0.15.3):

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

CombatLog action types in use as of v0.15.4: ``initiative``,
``turn_advance``, ``round_advance``, ``system``, ``attack``,
``health_change``, ``weapon_change``, ``armor_change``,
``cover_change``. Real-time fan-out (WebSocket broadcast) lands in
v0.15.6.
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


def _roll_pool(n):
    """Roll ``n`` d10s and count WoD 2.0 successes with 10-again explode.

    8/9/10 each count as one success; a rolled 10 also explodes and
    is re-rolled, with the exploded die also counting on 8+. The
    explosion chain is capped at five recursion levels per starting
    die so a (vanishingly unlikely) infinite-tens streak cannot stall
    the request loop.

    Returns ``(successes, raw_dice_list)``. ``raw_dice_list`` is the
    full sequence of faces rolled including any exploded dice — useful
    for surfacing the actual roll in the timeline payload.
    """
    if n <= 0:
        return 0, []
    dice = []
    successes = 0
    for _ in range(n):
        roll = _roll_d10()
        dice.append(roll)
        if roll >= 8:
            successes += 1
        # 10-again: keep rolling while we hit 10s, capped at 5 levels
        # of recursion so a pathological all-10s streak can't loop
        # indefinitely.
        depth = 0
        while roll == 10 and depth < 5:
            roll = _roll_d10()
            dice.append(roll)
            if roll >= 8:
                successes += 1
            depth += 1
    return successes, dice


def _compute_defense(participant):
    """Compute a target's defense pool.

    Override pinned on the participant wins unconditionally. Mooks
    return their ``mook_defense`` (``0`` if null). Character / NPC
    uses ``min(Dex, Wits) + Athletics`` per WoD 2.0 — same defensive
    ``try/except`` pattern as ``_compute_initiative`` so partial
    sheets don't crash the resolver.
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
            "weapon_choices": weapon_choices,
            "armor_choices": armor_choices,
            "cover_choices": cover_choices,
            "cover_by_tier": cover_by_tier,
            "attack_eligible": attack_eligible,
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


# ---------------------------------------------------------------------------
# Equip + cover (POST)  — v0.15.4
# ---------------------------------------------------------------------------


@login_required
@_gm_only
@csrf_protect
def equip_weapon(request, pk, participant_id):
    """POST — equip / unequip a weapon on a participant.

    ``weapon_name`` form field is matched against
    ``SiteSettings.get_weapons()`` (first match wins). Empty / not
    found clears the slot. The matched catalogue entry is *snapshotted*
    into ``participant.weapon_data`` so a later catalogue edit doesn't
    retroactively rewrite the in-flight encounter.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    encounter = get_object_or_404(Encounter, pk=pk)
    participant = get_object_or_404(
        Participant, pk=participant_id, encounter=encounter
    )

    name = request.POST.get("weapon_name", "").strip()

    if not name:
        # Empty submission = unequip.
        participant.weapon_name = ""
        participant.weapon_data = {}
        participant.save(update_fields=["weapon_name", "weapon_data"])
        _log(
            encounter,
            "weapon_change",
            f"{participant.name} unequipped weapon.",
            participant_id=participant.pk,
            weapon_name="",
        )
        return redirect("combat:detail", pk=encounter.pk)

    weapons = SiteSettings.load().get_weapons()
    entry = next((w for w in weapons if w.get("name") == name), None)

    if entry is None:
        # Unknown weapon — also clears the slot, so a stale POST
        # doesn't leave a half-equipped state behind.
        participant.weapon_name = ""
        participant.weapon_data = {}
        participant.save(update_fields=["weapon_name", "weapon_data"])
        _log(
            encounter,
            "weapon_change",
            f"{participant.name} unequipped weapon.",
            participant_id=participant.pk,
            weapon_name="",
        )
        return redirect("combat:detail", pk=encounter.pk)

    # Snapshot the full entry — defensive shallow copy so later
    # mutations on the catalogue list don't bleed in.
    participant.weapon_name = entry.get("name", "")
    participant.weapon_data = dict(entry)
    participant.save(update_fields=["weapon_name", "weapon_data"])

    _log(
        encounter,
        "weapon_change",
        f"{participant.name} equipped {participant.weapon_name}.",
        participant_id=participant.pk,
        weapon_name=participant.weapon_name,
    )
    return redirect("combat:detail", pk=encounter.pk)


@login_required
@_gm_only
@csrf_protect
def equip_armor(request, pk, participant_id):
    """POST — equip / unequip armor on a participant.

    Mirror of ``equip_weapon`` against ``SiteSettings.get_armor()``.
    Snapshot semantics are the same — catalogue edits do not mutate
    in-flight encounters.
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
@_gm_only
@csrf_protect
def set_cover(request, pk, participant_id):
    """POST — update a participant's cover state.

    ``cover_state`` (none/light/heavy/full) drives the attacker
    penalty in the resolver. ``cover_entry_name`` is an optional
    catalogue lookup against ``SiteSettings.get_cover()`` — when it
    matches, durability + health from the entry seed the cover's
    breach track (see v0.14.65 cover-destruction rules).
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
# Attack resolution (POST)  — v0.15.4
# ---------------------------------------------------------------------------


@login_required
@_gm_only
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
    * Faction is **not** checked — PvP is intentional. The GM can
      have a player target another player's character.

    The resolver writes one or two log rows depending on the outcome:

    * ``blocked_by_cover`` — full cover, no roll, no health change.
      Single ``attack`` row.
    * ``miss`` — pool rolled to zero successes. Single ``attack`` row.
    * ``hit`` — both ``attack`` (resolution payload) and
      ``health_change`` (so the timeline can be filtered to
      damage-only). Health applied to the matching B / L / A track,
      capped at ``health_max``; overflow is logged but no track
      upgrade is performed (that's v0.15.5).
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

    target_id = request.POST.get("target_id")
    if not target_id:
        messages.error(request, "Pick a target.")
        return redirect("combat:detail", pk=encounter.pk)
    target = get_object_or_404(
        Participant, pk=target_id, encounter=encounter
    )
    if target.id == attacker.id:
        messages.error(request, "Cannot attack self.")
        return redirect("combat:detail", pk=encounter.pk)

    gm_modifier_int = _safe_int(request.POST.get("gm_modifier"), 0)
    weapon_skill = request.POST.get("weapon_skill", "").strip()

    weapon_data = attacker.weapon_data or {}
    weapon_name = attacker.weapon_name or "(unarmed)"

    attack_pool = _attack_dice_pool(
        attacker, weapon_data, gm_modifier_int, weapon_skill,
    )
    defense = _compute_defense(target)
    cover_pen = _cover_penalty(target.cover_state)

    # ---- Full cover short-circuit -----------------------------------------
    if cover_pen == "BLOCKED":
        _log(
            encounter,
            "attack",
            f"{attacker.name} → {target.name}: BLOCKED BY FULL COVER.",
            actor_participant_id=attacker.id,
            target_participant_id=target.id,
            outcome="blocked_by_cover",
            attack_pool=attack_pool,
            defense=defense,
            cover_state=target.cover_state,
            successes=0,
            gm_modifier=gm_modifier_int,
            weapon_name=weapon_name,
            weapon_skill=weapon_skill,
        )
        return redirect("combat:detail", pk=encounter.pk)

    final_pool = max(0, attack_pool - defense - cover_pen)
    successes, dice = _roll_pool(final_pool)

    # ---- Miss --------------------------------------------------------------
    if successes == 0:
        _log(
            encounter,
            "attack",
            f"{attacker.name} attacks {target.name}: missed.",
            actor_participant_id=attacker.id,
            target_participant_id=target.id,
            outcome="miss",
            attack_pool=attack_pool,
            defense=defense,
            cover_pen=cover_pen,
            final_pool=final_pool,
            dice=dice,
            successes=0,
            gm_modifier=gm_modifier_int,
            weapon_name=weapon_name,
            weapon_skill=weapon_skill,
        )
        return redirect("combat:detail", pk=encounter.pk)

    # ---- Hit ---------------------------------------------------------------
    weapon_amount, damage_type_from_field = _parse_weapon_damage(
        weapon_data.get("damage", "")
    )
    # Allow an explicit override on the snapshot (future-proof for
    # weapons that diverge from the parsed string), else use the
    # parsed type. Default lethal.
    damage_type = (
        weapon_data.get("damage_type")
        or damage_type_from_field
        or "L"
    ).upper()
    if damage_type not in ("B", "L", "A"):
        damage_type = "L"

    raw_damage = successes + weapon_amount

    # Armor source depends on participant kind. Aggravated bypasses.
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

    # Apply to the matching health track, capped at health_max.
    track_field = {
        "B": "health_bashing",
        "L": "health_lethal",
        "A": "health_aggravated",
    }[damage_type]
    type_label = {"B": "bashing", "L": "lethal", "A": "aggravated"}[damage_type]

    current = getattr(target, track_field) or 0
    cap = target.health_max or 0
    proposed = current + final_damage
    overflow = max(0, proposed - cap) if cap else 0
    new_value = min(proposed, cap) if cap else proposed
    setattr(target, track_field, new_value)
    target.save(update_fields=[track_field])

    payload = dict(
        actor_participant_id=attacker.id,
        target_participant_id=target.id,
        outcome="hit",
        attack_pool=attack_pool,
        defense=defense,
        cover_pen=cover_pen,
        final_pool=final_pool,
        dice=dice,
        successes=successes,
        raw_damage=raw_damage,
        weapon_damage=weapon_amount,
        armor_reduction=armor_reduction,
        final_damage=final_damage,
        damage_type=damage_type,
        gm_modifier=gm_modifier_int,
        weapon_name=weapon_name,
        weapon_skill=weapon_skill,
        overflow=overflow,
    )

    _log(
        encounter,
        "attack",
        f"{attacker.name} hits {target.name} for {final_damage} {type_label} damage.",
        **payload,
    )
    # Separate health_change row so the timeline can be filtered
    # down to damage-only events without re-parsing attack payloads.
    _log(
        encounter,
        "health_change",
        f"{target.name} takes {final_damage} {type_label} damage.",
        **payload,
    )
    return redirect("combat:detail", pk=encounter.pk)
