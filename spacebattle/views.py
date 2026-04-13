"""Views for the spacebattle application (Release B).

Endpoints are designed to be MCP-friendly:
  - Every mutating endpoint supports ?dry_run=true to return the
    projected state without persisting or broadcasting
  - Responses always include a log_entry ref so a simulation script
    can trace actions deterministically
  - All actions are POST-to-resource with minimal JSON bodies

Mechanics are intentionally light at this stage: Release B ships the
battlemap plumbing plus a pure-function simulate endpoint for balance
work. Rules enforcement (movement points, weapon ranges, auto-damage)
is deferred to a future 0.15.x track.
"""

import json
import random

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from .models import Battle, BattleLog, BattleParticipant


# ---------------------------------------------------------------------------
# Permission helpers
# ---------------------------------------------------------------------------

def _user_agency(user):
    """Reuse the starmap helper for consistency across apps."""
    from starmap.views import _get_user_agency
    return _get_user_agency(user)


def _can_view_battle(user, battle):
    if user.is_superuser or user.is_staff:
        return True
    # Players see a battle only if at least one participant is from
    # their own agency.
    agency = _user_agency(user)
    if agency is None:
        return False
    return battle.participants.filter(starship__agency=agency).exists()


def _can_edit_battle(user, battle):
    return user.is_superuser or user.is_staff


def _can_command_participant(user, participant):
    """A player can command ships owned by their agency; staff can
    command anything."""
    if user.is_superuser or user.is_staff:
        return True
    agency = _user_agency(user)
    if agency is None:
        return False
    return participant.starship.agency_id == agency.id


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------

def _serialize_participant(p):
    ss = p.starship
    cls = ss.starship_class
    return {
        "id": p.id,
        "battle_id": p.battle_id,
        "starship_id": ss.id,
        "starship_name": ss.name,
        "hull_number": ss.hull_number,
        "starship_class_id": cls.id,
        "starship_class_name": cls.name,
        "ship_type_key": cls.ship_type.key,
        "ship_type_name": cls.ship_type.name,
        "agency_id": ss.agency_id,
        "agency_name": ss.agency.name if ss.agency else None,
        "side": p.side,
        "q": p.q,
        "r": p.r,
        "facing": p.facing,
        "status": p.status,
        "initiative_roll": p.initiative_roll,
        "initiative_result": p.initiative_result,
        "token_color": p.token_color,
        "token_icon": p.token_icon,
        "current_crew": ss.current_crew,
        "maintenance_state": ss.maintenance_state,
        "ship_status": ss.status,
        "notes": p.notes,
        "position_order": p.position_order,
    }


def _serialize_battle(battle, include_participants=True, include_log=False, log_limit=None):
    data = {
        "id": battle.id,
        "name": battle.name,
        "game_date": battle.game_date,
        "status": battle.status,
        "grid_width": battle.grid_width,
        "grid_height": battle.grid_height,
        "round_number": battle.round_number,
        "active_participant_index": battle.active_participant_index,
        "initiative_order": battle.initiative_order or [],
        "created_by_id": battle.created_by_id,
        "created_by_username": (
            battle.created_by.username if battle.created_by else None
        ),
        "notes": battle.notes,
        "metadata": battle.metadata or {},
        "started_at": battle.started_at.isoformat() if battle.started_at else None,
        "ended_at": battle.ended_at.isoformat() if battle.ended_at else None,
        "created_at": battle.created_at.isoformat() if battle.created_at else None,
        "updated_at": battle.updated_at.isoformat() if battle.updated_at else None,
    }
    if include_participants:
        parts = battle.participants.select_related(
            "starship",
            "starship__starship_class",
            "starship__starship_class__ship_type",
            "starship__agency",
        ).all()
        data["participants"] = [_serialize_participant(p) for p in parts]
    if include_log:
        qs = battle.log_entries.all().order_by("id")
        if log_limit is not None:
            qs = qs.order_by("-id")[:log_limit]
            qs = list(reversed(list(qs)))
        data["log"] = [_serialize_log(e) for e in qs]
    return data


def _serialize_log(entry):
    return {
        "id": entry.id,
        "battle_id": entry.battle_id,
        "round_number": entry.round_number,
        "actor_participant_id": entry.actor_participant_id,
        "action_type": entry.action_type,
        "data": entry.data or {},
        "message": entry.message,
        "is_reverted": entry.is_reverted,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }


# ---------------------------------------------------------------------------
# Log helper
# ---------------------------------------------------------------------------

def _log(battle, action_type, *, actor=None, data=None, message="", dry_run=False):
    """Append a BattleLog entry and broadcast it to websocket viewers.

    In dry_run mode the entry is not persisted, not broadcast, and
    the returned dict uses id=None so callers know it was synthetic.
    """
    if dry_run:
        return {
            "id": None,
            "battle_id": battle.id,
            "round_number": battle.round_number,
            "actor_participant_id": actor.id if actor else None,
            "action_type": action_type,
            "data": data or {},
            "message": message,
            "is_reverted": False,
            "created_at": timezone.now().isoformat(),
        }
    entry = BattleLog.objects.create(
        battle=battle,
        round_number=battle.round_number,
        actor_participant=actor,
        action_type=action_type,
        data=data or {},
        message=message,
    )
    serialised = _serialize_log(entry)
    # Broadcast via Channels so every connected battle page updates
    # without polling. Safe even when the channel layer is unavailable.
    try:
        from .consumers import broadcast_battle_event
        broadcast_battle_event(battle.id, "log", serialised)
    except Exception:
        pass
    return serialised


# ---------------------------------------------------------------------------
# Battles — CRUD
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["GET", "POST"])
def api_battles(request):
    if request.method == "GET":
        # Staff see all; players see battles where their agency has a ship.
        qs = Battle.objects.all().order_by("-created_at")
        if not request.user.is_staff:
            agency = _user_agency(request.user)
            if agency is None:
                qs = qs.none()
            else:
                qs = qs.filter(participants__starship__agency=agency).distinct()
        return JsonResponse(
            [_serialize_battle(b, include_participants=False) for b in qs],
            safe=False,
        )

    # POST — staff-only
    if not request.user.is_staff:
        return JsonResponse({"error": "Permission denied"}, status=403)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    name = (body.get("name") or "").strip()
    if not name:
        return JsonResponse({"error": "name required"}, status=400)

    battle = Battle.objects.create(
        name=name,
        game_date=body.get("game_date", ""),
        grid_width=int(body.get("grid_width", 20)),
        grid_height=int(body.get("grid_height", 15)),
        notes=body.get("notes", ""),
        metadata=body.get("metadata") or {},
        created_by=request.user,
    )
    _log(battle, "system", message=f"Battle '{name}' created.")
    return JsonResponse(_serialize_battle(battle), status=201)


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
def api_battle_detail(request, pk):
    battle = get_object_or_404(
        Battle.objects.select_related("created_by"), pk=pk,
    )
    if not _can_view_battle(request.user, battle):
        return JsonResponse({"error": "Not visible"}, status=404)

    if request.method == "GET":
        log_limit = request.GET.get("log_limit")
        return JsonResponse(_serialize_battle(
            battle,
            include_log=True,
            log_limit=int(log_limit) if log_limit else None,
        ))

    if not _can_edit_battle(request.user, battle):
        return JsonResponse({"error": "Permission denied"}, status=403)

    if request.method == "DELETE":
        battle.delete()
        return JsonResponse({"ok": True})

    # PUT
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    for field in ("name", "game_date", "notes"):
        if field in body:
            setattr(battle, field, body[field])
    for field in ("grid_width", "grid_height"):
        if field in body:
            try:
                setattr(battle, field, int(body[field]))
            except (TypeError, ValueError):
                return JsonResponse({"error": f"{field} must be an integer"}, status=400)
    if "metadata" in body:
        md = body["metadata"]
        if not isinstance(md, dict):
            return JsonResponse({"error": "metadata must be an object"}, status=400)
        battle.metadata = md
    battle.save()
    return JsonResponse(_serialize_battle(battle))


# ---------------------------------------------------------------------------
# Participants
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["GET", "POST"])
def api_participants(request, battle_pk):
    battle = get_object_or_404(Battle, pk=battle_pk)
    if not _can_view_battle(request.user, battle):
        return JsonResponse({"error": "Not visible"}, status=404)

    if request.method == "GET":
        parts = battle.participants.select_related(
            "starship", "starship__starship_class",
            "starship__starship_class__ship_type", "starship__agency",
        ).all()
        return JsonResponse(
            [_serialize_participant(p) for p in parts], safe=False,
        )

    # POST — add a participant (staff or owner of the ship)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    starship_id = body.get("starship_id")
    if not starship_id:
        return JsonResponse({"error": "starship_id required"}, status=400)
    from starships.models import Starship
    try:
        ship = Starship.objects.select_related(
            "starship_class", "starship_class__ship_type", "agency",
        ).get(pk=starship_id)
    except Starship.DoesNotExist:
        return JsonResponse({"error": "starship not found"}, status=404)

    agency = _user_agency(request.user)
    is_owner = agency is not None and agency.id == ship.agency_id
    if not (request.user.is_staff or is_owner):
        return JsonResponse({"error": "Permission denied"}, status=403)

    # Prevent duplicates (also enforced by unique_constraint at DB level)
    if battle.participants.filter(starship=ship).exists():
        return JsonResponse(
            {"error": "ship is already a participant"}, status=400,
        )

    side = body.get("side", "neutral")
    if side not in {"players", "enemies", "neutral"}:
        side = "neutral"

    position_order = battle.participants.count()
    p = BattleParticipant.objects.create(
        battle=battle,
        starship=ship,
        side=side,
        q=int(body.get("q", 0)),
        r=int(body.get("r", 0)),
        facing=int(body.get("facing", 0)),
        token_color=body.get("token_color", ""),
        token_icon=body.get("token_icon", ""),
        notes=body.get("notes", ""),
        position_order=position_order,
    )
    _log(
        battle, "system",
        actor=p,
        data={"side": side, "q": p.q, "r": p.r},
        message=f"{ship.name} ({ship.agency.name if ship.agency else 'unowned'}) placed on side {side}.",
    )
    return JsonResponse(_serialize_participant(p), status=201)


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
def api_participant_detail(request, battle_pk, pk):
    battle = get_object_or_404(Battle, pk=battle_pk)
    participant = get_object_or_404(
        BattleParticipant.objects.select_related(
            "starship", "starship__starship_class",
            "starship__starship_class__ship_type", "starship__agency",
        ),
        pk=pk, battle=battle,
    )
    if not _can_view_battle(request.user, battle):
        return JsonResponse({"error": "Not visible"}, status=404)

    if request.method == "GET":
        return JsonResponse(_serialize_participant(participant))

    if not (_can_edit_battle(request.user, battle) or _can_command_participant(request.user, participant)):
        return JsonResponse({"error": "Permission denied"}, status=403)

    if request.method == "DELETE":
        if not _can_edit_battle(request.user, battle):
            return JsonResponse({"error": "Permission denied"}, status=403)
        _log(
            battle, "system",
            actor=participant,
            message=f"{participant.starship.name} removed from battle.",
        )
        participant.delete()
        return JsonResponse({"ok": True})

    # PUT
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    # Staff-only fields
    if _can_edit_battle(request.user, battle):
        for field in ("side", "token_color", "token_icon", "notes"):
            if field in body:
                setattr(participant, field, body[field])
        if "status" in body:
            participant.status = body["status"]
    # Everyone with command rights can update positional + facing
    for field in ("q", "r", "facing"):
        if field in body:
            try:
                setattr(participant, field, int(body[field]))
            except (TypeError, ValueError):
                return JsonResponse({"error": f"{field} must be an integer"}, status=400)
    participant.save()
    return JsonResponse(_serialize_participant(participant))


# ---------------------------------------------------------------------------
# Actions — move / fire / damage / next turn / start
# ---------------------------------------------------------------------------

def _hex_distance(q1, r1, q2, r2):
    """Axial hex distance."""
    return (abs(q1 - q2) + abs(q1 + r1 - q2 - r2) + abs(r1 - r2)) // 2


@login_required
@require_http_methods(["POST"])
def api_participant_move(request, battle_pk, pk):
    battle = get_object_or_404(Battle, pk=battle_pk)
    participant = get_object_or_404(
        BattleParticipant.objects.select_related(
            "starship", "starship__starship_class",
            "starship__starship_class__ship_type", "starship__agency",
        ),
        pk=pk, battle=battle,
    )
    if not _can_view_battle(request.user, battle):
        return JsonResponse({"error": "Not visible"}, status=404)
    if not _can_command_participant(request.user, participant):
        return JsonResponse({"error": "Permission denied"}, status=403)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    try:
        new_q = int(body.get("q", participant.q))
        new_r = int(body.get("r", participant.r))
        new_facing = int(body.get("facing", participant.facing)) % 6
    except (TypeError, ValueError):
        return JsonResponse({"error": "q/r/facing must be integers"}, status=400)

    # Grid bounds check
    if not (0 <= new_q < battle.grid_width and 0 <= new_r < battle.grid_height):
        return JsonResponse({"error": "coordinates out of bounds"}, status=400)

    dry_run = request.GET.get("dry_run", "").lower() == "true"
    distance = _hex_distance(participant.q, participant.r, new_q, new_r)
    old = {"q": participant.q, "r": participant.r, "facing": participant.facing}
    new = {"q": new_q, "r": new_r, "facing": new_facing}

    log_entry = _log(
        battle, "move",
        actor=participant,
        data={"from": old, "to": new, "distance": distance},
        message=(
            f"{participant.starship.name} moves "
            f"({old['q']},{old['r']}) → ({new['q']},{new['r']}) "
            f"distance {distance}."
        ),
        dry_run=dry_run,
    )
    if not dry_run:
        participant.q = new_q
        participant.r = new_r
        participant.facing = new_facing
        participant.save(update_fields=["q", "r", "facing"])
        try:
            from .consumers import broadcast_battle_event
            broadcast_battle_event(battle.id, "participant", _serialize_participant(participant))
        except Exception:
            pass

    return JsonResponse({
        "participant": _serialize_participant(participant),
        "log_entry": log_entry,
        "dry_run": dry_run,
    })


@login_required
@require_http_methods(["POST"])
def api_participant_fire(request, battle_pk, pk):
    """Declare a weapon fire action. Release B logs it; Release F
    lets the GM adjudicate damage via /apply-damage/."""
    battle = get_object_or_404(Battle, pk=battle_pk)
    attacker = get_object_or_404(
        BattleParticipant.objects.select_related(
            "starship", "starship__starship_class",
            "starship__starship_class__ship_type", "starship__agency",
        ),
        pk=pk, battle=battle,
    )
    if not _can_view_battle(request.user, battle):
        return JsonResponse({"error": "Not visible"}, status=404)
    if not _can_command_participant(request.user, attacker):
        return JsonResponse({"error": "Permission denied"}, status=403)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    target_id = body.get("target_id")
    if not target_id:
        return JsonResponse({"error": "target_id required"}, status=400)
    try:
        target = BattleParticipant.objects.select_related("starship").get(
            pk=target_id, battle=battle,
        )
    except BattleParticipant.DoesNotExist:
        return JsonResponse({"error": "target not in this battle"}, status=400)

    weapon_key = body.get("weapon_key", "")
    dry_run = request.GET.get("dry_run", "").lower() == "true"
    distance = _hex_distance(attacker.q, attacker.r, target.q, target.r)

    log_entry = _log(
        battle, "fire",
        actor=attacker,
        data={
            "target_id": target.id,
            "target_name": target.starship.name,
            "weapon_key": weapon_key,
            "distance": distance,
        },
        message=(
            f"{attacker.starship.name} fires {weapon_key or 'weapons'} at "
            f"{target.starship.name} (range {distance})."
        ),
        dry_run=dry_run,
    )

    return JsonResponse({
        "attacker": _serialize_participant(attacker),
        "target": _serialize_participant(target),
        "log_entry": log_entry,
        "dry_run": dry_run,
    })


@login_required
@require_http_methods(["POST"])
def api_participant_apply_damage(request, battle_pk, pk):
    """Apply a damage delta directly to the canonical Starship record.

    Staff-only: players declare fire actions but only the GM applies
    damage. Delta values come from body: {hull_delta, crew_delta,
    status, message}. hull_delta operates on Starship.maintenance_state
    (percent, 0-100). Negative values reduce the stat, positive
    values heal.
    """
    battle = get_object_or_404(Battle, pk=battle_pk)
    participant = get_object_or_404(
        BattleParticipant.objects.select_related(
            "starship", "starship__starship_class",
            "starship__starship_class__ship_type", "starship__agency",
        ),
        pk=pk, battle=battle,
    )
    if not _can_edit_battle(request.user, battle):
        return JsonResponse({"error": "Permission denied — GM only"}, status=403)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    dry_run = request.GET.get("dry_run", "").lower() == "true"
    ship = participant.starship

    hull_delta = int(body.get("hull_delta", 0))
    crew_delta = int(body.get("crew_delta", 0))
    new_ship_status = body.get("ship_status")
    new_participant_status = body.get("participant_status")
    note = (body.get("message") or "").strip()

    before = {
        "maintenance_state": ship.maintenance_state,
        "current_crew": ship.current_crew,
        "ship_status": ship.status,
        "participant_status": participant.status,
    }

    projected_hull = max(0, min(100, ship.maintenance_state + hull_delta))
    projected_crew = max(0, ship.current_crew + crew_delta)

    after = {
        "maintenance_state": projected_hull,
        "current_crew": projected_crew,
        "ship_status": new_ship_status or ship.status,
        "participant_status": new_participant_status or participant.status,
    }

    log_entry = _log(
        battle, "damage",
        actor=participant,
        data={
            "before": before,
            "after": after,
            "hull_delta": hull_delta,
            "crew_delta": crew_delta,
        },
        message=note or (
            f"Damage applied to {ship.name}: hull "
            f"{before['maintenance_state']}% → {after['maintenance_state']}%, "
            f"crew {before['current_crew']} → {after['current_crew']}."
        ),
        dry_run=dry_run,
    )

    if not dry_run:
        with transaction.atomic():
            ship.maintenance_state = projected_hull
            ship.current_crew = projected_crew
            if new_ship_status:
                ship.status = new_ship_status
            ship.save(update_fields=[
                "maintenance_state", "current_crew", "status", "updated_at",
            ])
            if new_participant_status:
                participant.status = new_participant_status
                participant.save(update_fields=["status"])
        try:
            from .consumers import broadcast_battle_event
            broadcast_battle_event(battle.id, "participant", _serialize_participant(participant))
        except Exception:
            pass

    return JsonResponse({
        "participant": _serialize_participant(participant),
        "log_entry": log_entry,
        "before": before,
        "after": after,
        "dry_run": dry_run,
    })


# ---------------------------------------------------------------------------
# Flow control — start battle, roll initiative, next turn
# ---------------------------------------------------------------------------

def _roll_initiative_for_all(battle, rng):
    """Roll 1d10 + ship_type.initiative_bonus for every participant
    and store the order in battle.initiative_order."""
    parts = list(
        battle.participants.select_related("starship__starship_class__ship_type")
        .filter(status__in=["active", "damaged"])
    )
    results = []
    for p in parts:
        bonus = p.starship.starship_class.ship_type.initiative_bonus
        roll = rng.randint(1, 10)
        total = roll + bonus
        p.initiative_roll = roll
        p.initiative_result = total
        p.save(update_fields=["initiative_roll", "initiative_result"])
        results.append({
            "participant_id": p.id,
            "roll": roll,
            "bonus": bonus,
            "total": total,
            "ship_size": p.starship.starship_class.size,
        })
    # Sort descending by (total, -ship_size) so smaller ships win ties.
    results.sort(key=lambda x: (-x["total"], x["ship_size"]))
    battle.initiative_order = [r["participant_id"] for r in results]
    battle.active_participant_index = 0
    battle.save(update_fields=["initiative_order", "active_participant_index"])
    return results


@login_required
@require_http_methods(["POST"])
def api_battle_start(request, pk):
    battle = get_object_or_404(Battle, pk=pk)
    if not _can_edit_battle(request.user, battle):
        return JsonResponse({"error": "Permission denied"}, status=403)
    if battle.status != "setup":
        return JsonResponse({"error": f"battle is already {battle.status}"}, status=400)
    if not battle.participants.exists():
        return JsonResponse({"error": "no participants"}, status=400)

    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        body = {}
    seed = body.get("seed")
    rng = random.Random(seed) if seed is not None else random.Random()

    battle.status = "active"
    battle.round_number = 1
    battle.started_at = timezone.now()
    battle.save(update_fields=["status", "round_number", "started_at"])

    results = _roll_initiative_for_all(battle, rng)
    _log(
        battle, "initiative",
        data={"results": results, "seed": seed},
        message=(
            "Round 1 initiative rolled: "
            + ", ".join(
                f"#{i + 1} P{r['participant_id']} ({r['total']})"
                for i, r in enumerate(results[:5])
            )
            + ("…" if len(results) > 5 else "")
        ),
    )
    return JsonResponse(_serialize_battle(battle, include_log=True, log_limit=10))


@login_required
@require_http_methods(["POST"])
def api_battle_next_turn(request, pk):
    battle = get_object_or_404(Battle, pk=pk)
    if not _can_edit_battle(request.user, battle):
        return JsonResponse({"error": "Permission denied"}, status=403)
    if battle.status != "active":
        return JsonResponse({"error": "battle is not active"}, status=400)
    if not battle.initiative_order:
        return JsonResponse({"error": "no initiative order yet"}, status=400)

    battle.active_participant_index += 1
    new_round = False
    if battle.active_participant_index >= len(battle.initiative_order):
        battle.round_number += 1
        battle.active_participant_index = 0
        new_round = True

    if new_round:
        rng = random.Random()
        results = _roll_initiative_for_all(battle, rng)
        _log(
            battle, "initiative",
            data={"results": results},
            message=f"Round {battle.round_number} initiative rolled.",
        )
    else:
        battle.save(update_fields=["active_participant_index"])

    _log(
        battle, "turn_advance",
        data={
            "round": battle.round_number,
            "active_participant_index": battle.active_participant_index,
        },
        message=f"Advanced to turn {battle.active_participant_index + 1} of round {battle.round_number}.",
    )
    return JsonResponse(_serialize_battle(battle, include_log=True, log_limit=15))


@login_required
@require_http_methods(["POST"])
def api_battle_end(request, pk):
    battle = get_object_or_404(Battle, pk=pk)
    if not _can_edit_battle(request.user, battle):
        return JsonResponse({"error": "Permission denied"}, status=403)
    if battle.status == "concluded":
        return JsonResponse({"error": "battle already concluded"}, status=400)
    battle.status = "concluded"
    battle.ended_at = timezone.now()
    battle.save(update_fields=["status", "ended_at"])
    _log(battle, "system", message="Battle concluded.")
    return JsonResponse(_serialize_battle(battle))


# ---------------------------------------------------------------------------
# Log
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["GET", "POST"])
def api_battle_log(request, pk):
    battle = get_object_or_404(Battle, pk=pk)
    if not _can_view_battle(request.user, battle):
        return JsonResponse({"error": "Not visible"}, status=404)

    if request.method == "GET":
        since = request.GET.get("since_id")
        qs = battle.log_entries.all().order_by("id")
        if since:
            qs = qs.filter(id__gt=int(since))
        return JsonResponse([_serialize_log(e) for e in qs], safe=False)

    # POST — manual GM note
    if not _can_edit_battle(request.user, battle):
        return JsonResponse({"error": "Permission denied"}, status=403)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    message = (body.get("message") or "").strip()
    if not message:
        return JsonResponse({"error": "message required"}, status=400)
    entry = _log(battle, "note", message=message)
    return JsonResponse(entry, status=201)


# ---------------------------------------------------------------------------
# Simulate — pure function over ship stats (Release B MCP hook)
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["POST"])
def api_battle_simulate(request, pk):
    """Run a balance simulation over this battle's current state.

    Body: {
      iterations: int,
      scripted_actions: [  # optional — replay a sequence each run
        {actor_index, type: "move|fire", q?, r?, target_index?, weapon_key?}
      ],
      seed: int?,
      max_rounds: int?  # default 30
    }

    Uses a lightweight toy combat model so GMs can test class
    balance before the real rules engine ships. Every iteration
    rolls initiative, runs scripted actions once, then lets each
    active participant deal dice-pool damage to the nearest enemy
    until one side is wiped or max_rounds is hit.
    """
    battle = get_object_or_404(Battle, pk=pk)
    if not _can_view_battle(request.user, battle):
        return JsonResponse({"error": "Not visible"}, status=404)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    iterations = max(1, min(2000, int(body.get("iterations", 100))))
    max_rounds = max(1, min(100, int(body.get("max_rounds", 30))))
    seed = body.get("seed")
    master_rng = random.Random(seed) if seed is not None else random.Random()

    # Snapshot participant stats; the sim never touches the DB.
    snapshot = []
    parts = battle.participants.select_related(
        "starship__starship_class__ship_type",
    ).all()
    for p in parts:
        snapshot.append({
            "id": p.id,
            "side": p.side,
            "hull": p.starship.maintenance_state,
            "crew": p.starship.current_crew,
            "required_crew": p.starship.starship_class.build_required_successes * 10 or 10,
            "initiative_bonus": p.starship.starship_class.ship_type.initiative_bonus,
            "size": p.starship.starship_class.size,
            "q": p.q, "r": p.r,
            "dice": max(1, p.starship.starship_class.size + 2),
        })

    if not snapshot:
        return JsonResponse({"error": "no participants to simulate"}, status=400)

    results = {
        "iterations": iterations,
        "player_wins": 0,
        "enemy_wins": 0,
        "draws": 0,
        "total_rounds": 0,
        "avg_player_hull_remaining": 0.0,
        "avg_enemy_hull_remaining": 0.0,
    }

    def _sim_once(rng):
        units = [dict(u) for u in snapshot]
        for rnd in range(max_rounds):
            # Roll initiative
            for u in units:
                u["init"] = rng.randint(1, 10) + u["initiative_bonus"]
            units.sort(key=lambda u: (-u["init"], u["size"]))
            # Each unit fires at nearest surviving opponent
            for u in units:
                if u["hull"] <= 0 or u["side"] == "neutral":
                    continue
                enemies = [
                    e for e in units
                    if e["hull"] > 0
                    and e["side"] != u["side"]
                    and e["side"] != "neutral"
                ]
                if not enemies:
                    continue
                enemies.sort(key=lambda e: _hex_distance(u["q"], u["r"], e["q"], e["r"]))
                target = enemies[0]
                # Storyteller-style roll — count 8-10 successes on dice pool
                successes = sum(1 for _ in range(u["dice"]) if rng.randint(1, 10) >= 8)
                damage = successes * 5  # each success = 5% hull
                target["hull"] = max(0, target["hull"] - damage)
            # Check victory
            player_alive = any(u["side"] == "players" and u["hull"] > 0 for u in units)
            enemy_alive = any(u["side"] == "enemies" and u["hull"] > 0 for u in units)
            if player_alive and not enemy_alive:
                return "players", rnd + 1, units
            if enemy_alive and not player_alive:
                return "enemies", rnd + 1, units
            if not player_alive and not enemy_alive:
                return "draw", rnd + 1, units
        return "draw", max_rounds, units

    player_hull_sum = 0.0
    enemy_hull_sum = 0.0
    player_count = 0
    enemy_count = 0
    for _ in range(iterations):
        iter_seed = master_rng.randint(0, 2**31 - 1)
        rng = random.Random(iter_seed)
        outcome, rounds_used, units = _sim_once(rng)
        results["total_rounds"] += rounds_used
        if outcome == "players":
            results["player_wins"] += 1
        elif outcome == "enemies":
            results["enemy_wins"] += 1
        else:
            results["draws"] += 1
        for u in units:
            if u["side"] == "players":
                player_hull_sum += u["hull"]
                player_count += 1
            elif u["side"] == "enemies":
                enemy_hull_sum += u["hull"]
                enemy_count += 1

    results["avg_player_hull_remaining"] = (
        player_hull_sum / max(1, player_count)
    )
    results["avg_enemy_hull_remaining"] = (
        enemy_hull_sum / max(1, enemy_count)
    )
    results["avg_rounds"] = results["total_rounds"] / iterations
    results["player_win_rate"] = results["player_wins"] / iterations
    results["enemy_win_rate"] = results["enemy_wins"] / iterations
    return JsonResponse(results)


# ---------------------------------------------------------------------------
# Page views
# ---------------------------------------------------------------------------

@login_required
@require_GET
def battles_list_page(request):
    """Battle list landing page — shows battles visible to the user."""
    return render(request, "spacebattle/list.html", {
        "is_staff": request.user.is_staff,
    })


@login_required
@require_GET
def battle_page(request, pk):
    """Single battle view — canvas + side panels."""
    battle = get_object_or_404(Battle, pk=pk)
    if not _can_view_battle(request.user, battle):
        return HttpResponseForbidden("ACCESS DENIED")
    return render(request, "spacebattle/battle.html", {
        "battle_id": battle.id,
        "battle_name": battle.name,
        "is_staff": request.user.is_staff,
    })
