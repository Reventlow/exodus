"""Views for the starmap application."""

import json
import random
import urllib.request
import urllib.parse

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import StarSystem, AgencyScan, ScanRollLog
from .serializers import (
    serialize_star_system,
    serialize_agency_scan,
    compute_scan_brackets,
    SCAN_THRESHOLDS,
)


def _get_user_agency(user):
    """Find the user's player agency via character workspace assignment."""
    from agencies.models import Base
    char_ids = set(user.characters.values_list("id", flat=True))
    if not char_ids:
        return None
    for base in Base.objects.filter(agency__is_player_agency=True).select_related("agency"):
        for ws in base.workspaces or []:
            if ws.get("assignedType") == "character" and ws.get("assignedTo") in char_ids:
                return base.agency
    return None


# ---------------------------------------------------------------------------
# Page views
# ---------------------------------------------------------------------------

@login_required
def starmap_page(request):
    """3D star map page. Visible to staff or when enabled in settings."""
    from exodus.models import SiteSettings
    settings_obj = SiteSettings.load()
    if not request.user.is_staff:
        if not settings_obj.show_star_map:
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden("ACCESS DENIED. Star map not yet available.")
    # Tech gates — default off until the players discover them in-game.
    return render(request, "starmap/demo.html", {
        "SHOW_FTL_ROUTE_PLANNING": settings_obj.show_ftl_route_planning,
        "SHOW_EXOTIC_MATTER": settings_obj.show_exotic_matter,
        "SHOW_FTL_JUMPS": settings_obj.show_ftl_jumps or request.user.is_superuser,
    })


# ---------------------------------------------------------------------------
# Star system API
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["GET"])
def api_star_systems(request):
    """List all star systems with agency-filtered scan data."""
    stars = StarSystem.objects.select_related("claimed_by").all()

    agency = None
    agency_scans = {}
    if not request.user.is_superuser:
        agency = _get_user_agency(request.user)
    else:
        # GM: show all, but also load player agency scans for context
        agency = _get_user_agency(request.user)

    if agency:
        scans = AgencyScan.objects.filter(agency=agency, scan_level__gt=0)
        agency_scans = {s.star_system_id: s for s in scans}

    data = [
        serialize_star_system(star, agency=agency, user=request.user, agency_scans=agency_scans)
        for star in stars
    ]
    return JsonResponse(data, safe=False)


@login_required
@require_http_methods(["GET", "PUT"])
def api_star_system_detail(request, pk):
    """Get or update a single star system."""
    star = get_object_or_404(StarSystem.objects.select_related("claimed_by"), pk=pk)

    if request.method == "GET":
        agency = _get_user_agency(request.user)
        return JsonResponse(serialize_star_system(star, agency=agency, user=request.user))

    # PUT — superuser only
    if not request.user.is_superuser:
        return JsonResponse({"error": "Permission denied"}, status=403)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    for field in ["name", "spectral_type"]:
        if field in body:
            setattr(star, field, body[field])
    if "planets" in body:
        star.planets = body["planets"]
    if "resources" in body:
        # Accept either {key: int} (compact) or {key: {value: int}} (GM
        # serializer shape). Always store as compact integers so ground
        # truth stays shape-stable regardless of what the client sent.
        raw = body["resources"] or {}
        cleaned = {}
        for key, val in raw.items():
            if isinstance(val, dict):
                val = val.get("value", 0)
            try:
                cleaned[key] = int(val)
            except (TypeError, ValueError):
                return JsonResponse(
                    {"error": f"resources.{key} must be an integer"}, status=400,
                )
        star.resources = cleaned
    if "scanLevelTruth" in body:
        star.scan_level_truth = body["scanLevelTruth"]
    # Star-intel single source of truth (GM-set).
    if "discovered" in body:
        star.discovered = bool(body["discovered"])
    if "hasLivablePlanet" in body:
        star.has_livable_planet = bool(body["hasLivablePlanet"])
    if "difficultyMod" in body:
        try:
            star.difficulty_mod = max(-10, min(10, int(body["difficultyMod"])))
        except (TypeError, ValueError):
            return JsonResponse({"error": "difficultyMod must be an integer"}, status=400)
    star.save()
    return JsonResponse(serialize_star_system(star, user=request.user))


# ---------------------------------------------------------------------------
# Admin import
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["POST"])
def api_admin_import(request):
    """Import star catalog from POST body. Superuser only."""
    if not request.user.is_superuser:
        return JsonResponse({"error": "Permission denied"}, status=403)

    try:
        stars = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    created = 0
    for s in stars:
        _, was_created = StarSystem.objects.update_or_create(
            name=s["name"],
            defaults={
                "x": s.get("x", 0),
                "y": s.get("y", 0),
                "z": s.get("z", 0),
                "distance": s.get("dist", 0),
                "spectral_type": s.get("spectral", ""),
                "planets": s.get("planets", 0),
                "is_sol": s.get("isSol", False),
                "is_endgame": s.get("isEndgame", False),
                "resources": s.get("resources", {}),
                "scan_level_truth": s.get("scanLevel", 0),
            },
        )
        if was_created:
            created += 1

    return JsonResponse({"imported": len(stars), "created": created})


# ---------------------------------------------------------------------------
# Agency scans
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["GET", "POST"])
def api_agency_scan_list(request, pk):
    """List or create scan projects for an agency."""
    from agencies.models import Agency
    agency = get_object_or_404(Agency, pk=pk)

    if request.method == "GET":
        scans = AgencyScan.objects.filter(agency=agency).select_related("star_system")
        data = [serialize_agency_scan(s) for s in scans]
        return JsonResponse(data, safe=False)

    # POST — create scan project
    if not request.user.is_superuser:
        return JsonResponse({"error": "Permission denied"}, status=403)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    star_id = body.get("starSystemId")
    star = get_object_or_404(StarSystem, pk=star_id)

    scan, created = AgencyScan.objects.get_or_create(
        agency=agency,
        star_system=star,
        defaults={
            "player": body.get("player", ""),
            "base_id": body.get("baseId"),
            "base_name": body.get("baseName", ""),
            "metadata": body.get("metadata", {}),
            "required_successes": SCAN_THRESHOLDS.get(0, 3),
        },
    )
    if not created:
        # Update assignment
        if "player" in body:
            scan.player = body["player"]
        if "baseId" in body:
            scan.base_id = body["baseId"]
        if "baseName" in body:
            scan.base_name = body["baseName"]
        if "metadata" in body:
            scan.metadata = body["metadata"]
        scan.save()

    return JsonResponse(serialize_agency_scan(scan), status=201 if created else 200)


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
def api_agency_scan_detail(request, pk, scan_id):
    """Get, update, or delete a scan project."""
    scan = get_object_or_404(
        AgencyScan.objects.select_related("star_system"),
        pk=scan_id, agency_id=pk,
    )

    if request.method == "GET":
        return JsonResponse(serialize_agency_scan(scan))

    if not request.user.is_superuser:
        return JsonResponse({"error": "Permission denied"}, status=403)

    if request.method == "DELETE":
        scan.delete()
        return JsonResponse({"ok": True})

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    if "player" in body:
        scan.player = body["player"]
    if "baseId" in body:
        scan.base_id = body["baseId"]
    if "baseName" in body:
        scan.base_name = body["baseName"]
    if "metadata" in body:
        scan.metadata = body["metadata"]
    if "scanLevel" in body:
        scan.scan_level = body["scanLevel"]
    if "currentSuccesses" in body:
        scan.current_successes = body["currentSuccesses"]
    scan.save()
    return JsonResponse(serialize_agency_scan(scan))


@login_required
@require_http_methods(["POST"])
def api_scan_roll(request, pk, scan_id):
    """Perform a scan roll on a star system."""
    from agencies.models import Agency
    from characters.models import Character

    agency = get_object_or_404(Agency, pk=pk)
    scan = get_object_or_404(
        AgencyScan.objects.select_related("star_system"),
        pk=scan_id, agency_id=pk,
    )

    if scan.scan_level >= 3:
        return JsonResponse({"error": "Already at maximum scan depth."}, status=400)

    char = Character.objects.filter(owner=request.user).first()
    char_name = char.name if char else "GM"

    # Check roll allocation
    rolls_data = agency.project_rolls or {}
    personal = rolls_data.get(char_name, {})
    total_free = personal.get("free", 0) or 0
    total_spare = personal.get("spare", 0) or 0

    if total_free <= 0 and total_spare <= 0 and not request.user.is_superuser:
        return JsonResponse({"error": "No rolls available."}, status=400)

    roll_type = "free" if total_free > 0 else "spare"
    if roll_type == "free":
        personal["free"] = total_free - 1
    else:
        personal["spare"] = total_spare - 1
    rolls_data[char_name] = personal

    # Mental load for spare rolls
    mental_damage = False
    if roll_type == "spare" and char:
        char.mental_load = (char.mental_load or 0) + 1
        char.save(update_fields=["mental_load"])
        mental_damage = True

    # Compute dice pool
    pool = 1
    meta = scan.metadata or {}

    # Character: Intelligence + Science
    if char:
        intelligence = char.attributes.get("power", {}).get("mental", 1)
        science = char.skills.get("mental", {}).get("Science", 0)
        pool = intelligence + science

    # Observatory level bonus (+2/+4/+6)
    observatory_bonus = meta.get("observatoryLevel", 0) * 2
    pool += observatory_bonus

    # Computer core bonus (+1/+2/+3)
    computer_bonus = meta.get("computerCoreLevel", 0)
    pool += computer_bonus

    # Tech bonus (GM configurable)
    tech_bonus = meta.get("techBonus", 0)
    pool += tech_bonus

    pool = max(pool, 1)

    # Roll dice (WoD: d10, 8+ success, 10 explodes)
    successes = 0
    rolls = []
    dice_left = pool
    while dice_left > 0:
        explosions = 0
        for _ in range(dice_left):
            die = random.randint(1, 10)
            rolls.append(die)
            if die >= 8:
                successes += 1
            if die >= 10:
                explosions += 1
        dice_left = explosions

    # Accumulate successes
    old_level = scan.scan_level
    scan.current_successes += successes

    # Check level up
    threshold = SCAN_THRESHOLDS.get(scan.scan_level, 999)
    new_level = scan.scan_level
    if scan.current_successes >= threshold and scan.scan_level < 3:
        scan.scan_level += 1
        new_level = scan.scan_level
        scan.current_successes = 0
        scan.required_successes = SCAN_THRESHOLDS.get(scan.scan_level, 999)

        # Compute scanned-resource brackets. Seed keeps a given (agency,
        # system) pair deterministic across re-scans.
        seed = scan.agency_id * 10000 + scan.star_system_id
        scan.scanned_resources = compute_scan_brackets(
            scan.star_system.resources, scan.scan_level, seed,
        )

    scan.save()
    agency.project_rolls = rolls_data
    agency.save(update_fields=["project_rolls"])

    # Build message
    msg = f"{roll_type.title()} scan: {pool} dice → {successes} successes."
    if new_level > old_level:
        labels = {1: "SURVEY", 2: "FOCUSED", 3: "DEEP"}
        msg += f" SCAN LEVEL UP: {labels.get(new_level, '?')}!"
    else:
        msg += f" Progress: {scan.current_successes}/{scan.required_successes}"
    if mental_damage:
        msg += f" {char_name} takes 1 mental load."

    # Log the roll
    ScanRollLog.objects.create(
        agency=agency,
        scan=scan,
        star_system_name=scan.star_system.name,
        character_name=char_name,
        roll_type=roll_type,
        pool=pool,
        rolls=rolls,
        successes=successes,
        old_level=old_level,
        new_level=new_level,
        message=msg,
    )

    return JsonResponse({
        "rollType": roll_type,
        "pool": pool,
        "rolls": rolls,
        "successes": successes,
        "mentalDamage": mental_damage,
        "oldLevel": old_level,
        "newLevel": new_level,
        "currentSuccesses": scan.current_successes,
        "requiredSuccesses": scan.required_successes,
        "scannedResources": scan.scanned_resources if new_level > old_level else None,
        "message": msg,
    })


def _count_false_records(star):
    """Active false public records for a system (raises the scan target).
    Returns 0 until the public-record model exists (Phase 3)."""
    try:
        from .models import PublicScanRecord
    except ImportError:
        return 0
    return PublicScanRecord.objects.filter(star_system=star, is_false=True).count()


@login_required
@require_http_methods(["POST"])
def api_observatory_scan(request, pk):
    """Star-intel scan: a declared observatory scans a discovered system.

    Body: {starSystemId, baseId}. Gated (like project rolls) on the GM having
    granted the agency scans: each observatory may scan ``Agency.scan_grant``
    times, tracked in ``Agency.scan_usage`` {baseId: count}. Also requires the
    system discovered and the observatory belonging to the agency. Rolls the
    observatory's dice (5/10/15), accumulates successes toward the system
    target, and recomputes uncertainty% + the approximate readout.
    """
    from django.db import transaction
    from agencies.models import Agency
    from characters.models import Character
    from .serializers import (
        effective_scan_target, scan_uncertainty, approx_resources,
        list_agency_observatories,
    )

    agency = get_object_or_404(Agency, pk=pk)
    if not request.user.is_superuser and _get_user_agency(request.user) != agency:
        return JsonResponse({"error": "Permission denied"}, status=403)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    star_id = body.get("starSystemId")
    base_id = body.get("baseId")
    if not star_id or not base_id:
        return JsonResponse({"error": "starSystemId and baseId required"}, status=400)

    star = get_object_or_404(StarSystem, pk=star_id)
    if not star.discovered and not request.user.is_superuser:
        return JsonResponse({"error": "System has not been discovered yet."}, status=400)

    # Resolve the declared observatory and its dice (must belong to the agency).
    observatories = {o["baseId"]: o for o in list_agency_observatories(agency)}
    obs = observatories.get(int(base_id))
    if not obs:
        return JsonResponse({"error": "That base has no observatory for this agency."}, status=400)

    # Roll allowance — each observatory may scan scan_grant times (GM grant).
    usage = agency.scan_usage or {}
    used = int(usage.get(str(base_id), 0) or 0)
    if used >= (agency.scan_grant or 0) and not request.user.is_superuser:
        return JsonResponse(
            {"error": "No scans remaining for this observatory. Ask the GM for a scan grant."},
            status=400,
        )

    # Roll the observatory's dice — WoD d10, 8+ success, 10 explodes.
    pool = int(obs["dice"])
    successes = 0
    rolls = []
    dice_left = pool
    while dice_left > 0:
        explosions = 0
        for _ in range(dice_left):
            die = random.randint(1, 10)
            rolls.append(die)
            if die >= 8:
                successes += 1
            if die >= 10:
                explosions += 1
        dice_left = explosions

    char = Character.objects.filter(owner=request.user).first()
    char_name = char.name if char else "GM"

    with transaction.atomic():
        scan, _ = AgencyScan.objects.get_or_create(
            agency=agency, star_system=star,
            defaults={"base_id": base_id, "base_name": obs["baseName"]},
        )
        before = scan.current_successes
        scan.current_successes = before + successes  # monotonic, never reset

        target = effective_scan_target(star, _count_false_records(star))
        scan.required_successes = target
        uncertainty = scan_uncertainty(scan.current_successes, target)
        seed = scan.agency_id * 10000 + scan.star_system_id
        scan.scanned_resources = approx_resources(star.resources, uncertainty, seed)
        scan.base_id = base_id
        scan.base_name = obs["baseName"]
        scan.save()

        usage[str(base_id)] = used + 1
        agency.scan_usage = usage
        agency.save(update_fields=["scan_usage"])

        msg = (f"{obs['baseName']} observatory ({pool} dice) → {successes} successes. "
               f"{scan.current_successes}/{target} ({uncertainty}% uncertainty).")
        try:
            ScanRollLog.objects.create(
                agency=agency, scan=scan, star_system_name=star.name,
                character_name=char_name, roll_type="observatory",
                pool=pool, rolls=rolls, successes=successes,
                old_level=before, new_level=scan.current_successes, message=msg,
            )
        except Exception:
            pass

    return JsonResponse({
        "pool": pool,
        "rolls": rolls,
        "successes": successes,
        "accumulated": scan.current_successes,
        "target": target,
        "uncertainty": uncertainty,
        "scannedResources": scan.scanned_resources,
        "hasLivablePlanet": (star.has_livable_planet if uncertainty <= 40 else None),
        "message": msg,
    })


@login_required
@require_http_methods(["POST"])
def api_publish_scan(request, pk):
    """Publish an agency's scan readout for a system to the public record, or
    publish FALSE data. Body: {starSystemId, isFalse?, payload?, uncertainty?}.

    Real publish snapshots the agency's current AgencyScan readout + uncertainty.
    A false publish takes a GM/player-authored payload + a (faked) uncertainty.
    """
    from agencies.models import Agency
    from .models import PublicScanRecord
    from .serializers import effective_scan_target, scan_uncertainty

    agency = get_object_or_404(Agency, pk=pk)
    if not request.user.is_superuser and _get_user_agency(request.user) != agency:
        return JsonResponse({"error": "Permission denied"}, status=403)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    star = get_object_or_404(StarSystem, pk=body.get("starSystemId"))
    is_false = bool(body.get("isFalse", False))

    if is_false:
        payload = body.get("payload") or {}
        uncertainty = int(body.get("uncertainty", 0))
    else:
        scan = AgencyScan.objects.filter(agency=agency, star_system=star).first()
        if not scan or scan.current_successes <= 0:
            return JsonResponse({"error": "No scan data to publish for this system."}, status=400)
        target = scan.required_successes or effective_scan_target(star)
        uncertainty = scan_uncertainty(scan.current_successes, target)
        payload = {
            "resources": scan.scanned_resources,
            "livable": (star.has_livable_planet if uncertainty <= 40 else None),
        }

    rec, _ = PublicScanRecord.objects.update_or_create(
        agency=agency, star_system=star,
        defaults={"is_false": is_false, "uncertainty": uncertainty, "payload": payload},
    )
    return JsonResponse({"ok": True, "isFalse": rec.is_false, "uncertainty": rec.uncertainty})


@login_required
@require_http_methods(["POST"])
def api_unpublish_scan(request, pk):
    """Remove an agency's public record for a system (keep it private)."""
    from agencies.models import Agency
    from .models import PublicScanRecord

    agency = get_object_or_404(Agency, pk=pk)
    if not request.user.is_superuser and _get_user_agency(request.user) != agency:
        return JsonResponse({"error": "Permission denied"}, status=403)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    PublicScanRecord.objects.filter(
        agency=agency, star_system_id=body.get("starSystemId"),
    ).delete()
    return JsonResponse({"ok": True})


@login_required
@require_http_methods(["GET"])
def api_scan_roll_log(request, pk, scan_id):
    """Get roll log for a scan project."""
    scan = get_object_or_404(AgencyScan, pk=scan_id, agency_id=pk)
    logs = scan.roll_logs.all()[:50]
    data = [
        {
            "id": log.id,
            "characterName": log.character_name,
            "rollType": log.roll_type,
            "pool": log.pool,
            "rolls": log.rolls,
            "successes": log.successes,
            "oldLevel": log.old_level,
            "newLevel": log.new_level,
            "message": log.message,
            "rolledAt": log.rolled_at.isoformat(),
        }
        for log in logs
    ]
    return JsonResponse(data, safe=False)


@login_required
@require_http_methods(["POST"])
def api_scan_meta(request, pk, scan_id):
    """Update scan project metadata."""
    if not request.user.is_superuser:
        return JsonResponse({"error": "Permission denied"}, status=403)

    scan = get_object_or_404(AgencyScan, pk=scan_id, agency_id=pk)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    scan.metadata = body.get("metadata", scan.metadata)
    if "player" in body:
        scan.player = body["player"]
    if "baseId" in body:
        scan.base_id = body["baseId"]
    if "baseName" in body:
        scan.base_name = body["baseName"]
    scan.save()
    return JsonResponse(serialize_agency_scan(scan))


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["POST"])
def api_claim_system(request, pk):
    """Claim a star system for an agency."""
    star = get_object_or_404(StarSystem, pk=pk)

    if star.claimed_by_id:
        return JsonResponse({"error": "System already claimed."}, status=400)
    if star.is_sol or star.is_endgame:
        return JsonResponse({"error": "Cannot claim this system."}, status=400)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        body = {}

    agency_id = body.get("agencyId")
    if not agency_id:
        return JsonResponse({"error": "agencyId required."}, status=400)

    from agencies.models import Agency
    agency = get_object_or_404(Agency, pk=agency_id)

    # Require at least survey scan
    has_scan = AgencyScan.objects.filter(
        agency=agency, star_system=star, scan_level__gte=1
    ).exists()
    if not has_scan and not request.user.is_superuser:
        return JsonResponse({"error": "Requires at least survey-level scan."}, status=400)

    star.claimed_by = agency
    star.claimed_at = timezone.now()
    star.save(update_fields=["claimed_by", "claimed_at"])

    return JsonResponse(serialize_star_system(star, user=request.user))


@login_required
@require_http_methods(["POST"])
def api_extract_resource(request, pk):
    """Extract a system resource into the claiming agency's FTL fuel/spares pool.

    Body: {agencyId, resourceKey, amount}. Requires the system claimed by the
    agency and scanned to ``extract_scan_level`` (superuser bypasses both). The
    resource must be configured as a fuel or spares key in jump_economy_config.
    Decrements StarSystem.resources in place and credits the pool via F().
    """
    from django.db import transaction
    from django.db.models import F
    from agencies.models import Agency
    from exodus.models import SiteSettings
    from starships.models import JumpLog

    star = get_object_or_404(StarSystem, pk=pk)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    agency_id = body.get("agencyId")
    resource_key = body.get("resourceKey")
    try:
        amount = int(body.get("amount", 0))
    except (TypeError, ValueError):
        return JsonResponse({"error": "amount must be an integer"}, status=400)
    if not agency_id or not resource_key:
        return JsonResponse({"error": "agencyId and resourceKey required"}, status=400)
    if amount <= 0:
        return JsonResponse({"error": "amount must be positive"}, status=400)

    agency = get_object_or_404(Agency, pk=agency_id)
    if not request.user.is_superuser and _get_user_agency(request.user) != agency:
        return JsonResponse({"error": "Permission denied"}, status=403)

    cfg = SiteSettings.load().get_jump_economy()
    fuel_keys = cfg.get("fuel_keys") or []
    spares_keys = cfg.get("spares_keys") or []
    if resource_key in fuel_keys:
        pool = "ftl_fuel"
    elif resource_key in spares_keys:
        pool = "ftl_spares"
    else:
        return JsonResponse(
            {"error": "Resource is not configured as fuel or spares."}, status=400,
        )

    if not request.user.is_superuser:
        if star.claimed_by_id != agency.id:
            return JsonResponse({"error": "Claim the system before extracting."}, status=400)
        need = int(cfg.get("extract_scan_level", 2))
        has_scan = AgencyScan.objects.filter(
            agency=agency, star_system=star, scan_level__gte=need,
        ).exists()
        if not has_scan:
            return JsonResponse(
                {"error": f"Requires scan level {need} to extract."}, status=400,
            )

    resources = dict(star.resources or {})
    available = int(resources.get(resource_key, 0) or 0)
    if available <= 0:
        return JsonResponse({"error": "No such resource available here."}, status=400)
    moved = min(amount, available)

    with transaction.atomic():
        resources[resource_key] = available - moved
        star.resources = resources
        star.save(update_fields=["resources", "updated_at"])
        Agency.objects.filter(pk=agency.id).update(**{pool: F(pool) + moved})
        agency.refresh_from_db(fields=["ftl_fuel", "ftl_spares"])
        JumpLog.objects.create(
            agency=agency, kind="extract",
            from_system_name=star.name, to_system_name=star.name,
            distance_ly=0, maintenance_basis=0, wear=0,
            costs={resource_key: -moved, pool: moved},  # negative resource = credit
            reason=f"Extracted {moved} {resource_key} -> {pool} at {star.name}",
        )

    return JsonResponse({
        "extracted": {resource_key: moved},
        "pool": pool,
        "agency": {"ftlFuel": agency.ftl_fuel, "ftlSpares": agency.ftl_spares},
    })


# ---------------------------------------------------------------------------
# Scan data sharing
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["POST"])
def api_share_scan(request, pk, scan_id):
    """Share scan data with another agency. Copies scan level and resources."""
    if not request.user.is_superuser:
        return JsonResponse({"error": "Permission denied"}, status=403)

    source_scan = get_object_or_404(
        AgencyScan.objects.select_related("star_system"),
        pk=scan_id, agency_id=pk,
    )

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    target_agency_id = body.get("targetAgencyId")
    if not target_agency_id:
        return JsonResponse({"error": "targetAgencyId required."}, status=400)

    from agencies.models import Agency
    target_agency = get_object_or_404(Agency, pk=target_agency_id)

    target_scan, _ = AgencyScan.objects.update_or_create(
        agency=target_agency,
        star_system=source_scan.star_system,
        defaults={
            "scan_level": source_scan.scan_level,
            "scanned_resources": source_scan.scanned_resources,
            "current_successes": 0,
            "required_successes": SCAN_THRESHOLDS.get(source_scan.scan_level, 999),
        },
    )

    return JsonResponse(serialize_agency_scan(target_scan))


# ---------------------------------------------------------------------------
# City Maps
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Seed Star Systems
# ---------------------------------------------------------------------------

# Scarcity dials the galaxy-wide abundance of a category. res_factor
# multiplies each ResourceType's typical_max so a "very common" galaxy yields
# full ranges while a "extremely rare" galaxy compresses them. planet/life/civ
# are independent presence probabilities (unchanged).
SCARCITY_CONFIG = {
    1: {"label": "Very Common",    "res_factor": 1.00, "planet": 0.80, "life": 0.40, "civ": 0.25},
    2: {"label": "Common",         "res_factor": 0.85, "planet": 0.60, "life": 0.25, "civ": 0.15},
    3: {"label": "Uncommon",       "res_factor": 0.65, "planet": 0.40, "life": 0.15, "civ": 0.08},
    4: {"label": "Rare",           "res_factor": 0.45, "planet": 0.25, "life": 0.08, "civ": 0.04},
    5: {"label": "Really Rare",    "res_factor": 0.28, "planet": 0.15, "life": 0.04, "civ": 0.02},
    6: {"label": "Extremely Rare", "res_factor": 0.15, "planet": 0.08, "life": 0.02, "civ": 0.01},
}

LIFE_WEIGHTS = [
    ("bacterial", 50), ("cellular", 25), ("plant", 15),
    ("animal", 8), ("intelligent", 2),
]

PLANET_TYPES_BY_SPECTRAL = {
    "O": [("gas_giant", 50), ("terrestrial", 20), ("ice_giant", 20), ("lava_world", 10)],
    "B": [("gas_giant", 50), ("terrestrial", 20), ("ice_giant", 20), ("lava_world", 10)],
    "A": [("gas_giant", 40), ("terrestrial", 25), ("ice_giant", 25), ("lava_world", 10)],
    "F": [("terrestrial", 35), ("gas_giant", 30), ("ocean_world", 15), ("ice_giant", 20)],
    "G": [("terrestrial", 40), ("gas_giant", 25), ("ocean_world", 20), ("ice_giant", 15)],
    "K": [("terrestrial", 45), ("ocean_world", 20), ("ice_giant", 20), ("gas_giant", 15)],
    "M": [("terrestrial", 40), ("ice_giant", 25), ("ocean_world", 20), ("dwarf", 15)],
    "L": [("dwarf", 50), ("ice_giant", 30), ("terrestrial", 20)],
    "T": [("dwarf", 60), ("ice_giant", 30), ("terrestrial", 10)],
    "Y": [("dwarf", 70), ("ice_giant", 30)],
    "D": [("dwarf", 50), ("terrestrial", 30), ("lava_world", 20)],
}

ATMO_BY_TYPE = {
    "terrestrial": [("nitrogen", 30), ("co2", 25), ("oxygen", 10), ("methane", 10), ("argon", 5), ("toxic", 10), ("none", 10)],
    "ocean_world":  [("nitrogen", 30), ("oxygen", 20), ("co2", 20), ("methane", 15), ("ammonia", 10), ("argon", 5)],
    "gas_giant":    [("hydrogen", 80), ("ammonia", 15), ("methane", 5)],
    "ice_giant":    [("hydrogen", 50), ("methane", 30), ("ammonia", 20)],
    "lava_world":   [("co2", 40), ("toxic", 40), ("none", 20)],
    "dwarf":        [("none", 60), ("co2", 20), ("nitrogen", 10), ("methane", 10)],
}

TEMP_BY_TYPE = {
    "terrestrial": ["-60°C to -10°C", "-20°C to 30°C", "10°C to 50°C", "0°C to 40°C"],
    "ocean_world":  ["-5°C to 25°C", "5°C to 35°C", "0°C to 20°C"],
    "gas_giant":    ["-200°C to -100°C", "-150°C to -50°C"],
    "ice_giant":    ["-220°C to -180°C", "-200°C to -150°C"],
    "lava_world":   ["200°C to 800°C", "400°C to 1200°C"],
    "dwarf":        ["-250°C to -100°C", "-180°C to -60°C"],
}

GRAVITY_BY_TYPE = {
    "terrestrial": ["0.3g", "0.6g", "0.8g", "1.0g", "1.2g", "1.5g"],
    "ocean_world":  ["0.7g", "0.9g", "1.0g", "1.1g"],
    "gas_giant":    ["2.0g", "2.5g", "3.0g", "5.0g"],
    "ice_giant":    ["1.0g", "1.5g", "2.0g"],
    "lava_world":   ["0.8g", "1.0g", "1.3g"],
    "dwarf":        ["0.05g", "0.1g", "0.2g", "0.3g"],
}


def _weighted_choice(options):
    """Pick from [(value, weight), ...] list."""
    total = sum(w for _, w in options)
    r = random.uniform(0, total)
    cumulative = 0
    for value, weight in options:
        cumulative += weight
        if r <= cumulative:
            return value
    return options[-1][0]


@login_required
@require_http_methods(["POST"])
def api_seed_systems(request):
    """Seed all star systems with resources, planets, and civilisations. Superuser only."""
    if not request.user.is_superuser:
        return JsonResponse({"error": "Permission denied"}, status=403)

    from .models import ResourceType, Civilisation, Planet, StarSystemCivilisation

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    res_scarcity = SCARCITY_CONFIG.get(body.get("resourceScarcity", 3), SCARCITY_CONFIG[3])
    planet_scarcity = SCARCITY_CONFIG.get(body.get("planetScarcity", 3), SCARCITY_CONFIG[3])
    life_level = body.get("lifeScarcity", 4)
    civ_level = body.get("civScarcity", 5)
    life_scarcity = SCARCITY_CONFIG.get(life_level, SCARCITY_CONFIG[4]) if life_level > 0 else None
    civ_scarcity = SCARCITY_CONFIG.get(civ_level, SCARCITY_CONFIG[5]) if civ_level > 0 else None

    resource_types = list(ResourceType.objects.all())
    civilisations = list(Civilisation.objects.all())
    stars = StarSystem.objects.all()

    # Full overwrite — wipe existing
    Planet.objects.all().delete()
    StarSystemCivilisation.objects.all().delete()

    total_planets = 0
    total_civs = 0
    total_seeded = 0

    for star in stars:
        if star.is_sol or star.is_endgame:
            continue

        # --- Resources ---
        # Each ResourceType has its own galaxy-wide range and rarity weight.
        # Scarcity compresses the upper bound and reduces presence odds.
        factor = res_scarcity["res_factor"]
        resources = {}
        for rt in resource_types:
            present_chance = min(1.0, rt.rarity_weight * (0.5 + factor))
            if random.random() > present_chance:
                resources[rt.key] = 0
                continue
            lo = rt.typical_min
            hi = max(lo, round(rt.typical_max * factor))
            resources[rt.key] = random.randint(lo, hi)
        star.resources = resources
        star.save(update_fields=["resources"])

        spectral_first = star.spectral_type[0].upper() if star.spectral_type else "M"
        planet_type_weights = PLANET_TYPES_BY_SPECTRAL.get(spectral_first, PLANET_TYPES_BY_SPECTRAL["M"])

        # --- Planets ---
        if random.random() < planet_scarcity["planet"]:
            # 1-3 planets, weighted toward fewer at higher scarcity
            max_planets = 3 if planet_scarcity["planet"] > 0.5 else 2 if planet_scarcity["planet"] > 0.2 else 1
            num_planets = random.randint(1, max_planets)
            letters = "bcdefgh"

            for i in range(num_planets):
                p_type = _weighted_choice(planet_type_weights)
                atmo_weights = ATMO_BY_TYPE.get(p_type, [("unknown", 100)])
                atmo = _weighted_choice(atmo_weights)
                temp_opts = TEMP_BY_TYPE.get(p_type, ["-100°C to 0°C"])
                grav_opts = GRAVITY_BY_TYPE.get(p_type, ["1.0g"])

                # Life
                life_type = "none"
                if life_scarcity:
                    has_life = random.random() < life_scarcity["life"]
                    if has_life and atmo not in ("none", "hydrogen"):
                        life_type = _weighted_choice(LIFE_WEIGHTS)

                # Water & habitability
                water = atmo in ("oxygen", "nitrogen", "co2") and p_type in ("terrestrial", "ocean_world") and random.random() < 0.3
                habitable = atmo in ("oxygen", "nitrogen") and water and p_type in ("terrestrial", "ocean_world")

                atmo_details = ""
                if atmo == "oxygen":
                    atmo_details = f"{random.randint(15, 25)}% O₂, {random.randint(65, 80)}% N₂, {random.randint(1, 5)}% Ar"
                elif atmo == "nitrogen":
                    atmo_details = f"{random.randint(85, 98)}% N₂, {random.randint(1, 10)}% CO₂"
                elif atmo == "co2":
                    atmo_details = f"{random.randint(80, 96)}% CO₂, {random.randint(2, 15)}% N₂"

                Planet.objects.create(
                    star_system=star,
                    name=f"{star.name} {letters[i]}",
                    orbital_position=i + 1,
                    planet_type=p_type,
                    atmosphere=atmo,
                    atmosphere_details=atmo_details,
                    life_type=life_type,
                    temperature_range=random.choice(temp_opts),
                    gravity=random.choice(grav_opts),
                    water=water,
                    habitable=habitable,
                    is_hidden=True,
                    scan_level_required=1 if p_type in ("gas_giant", "ice_giant") else 2,
                )
                total_planets += 1

        # --- Civilisations ---
        if civ_scarcity and civilisations and random.random() < civ_scarcity["civ"]:
            civ = random.choice(civilisations)
            scan_req = 3 if civ.tech_level in ("type_ii", "type_iii") else 2
            StarSystemCivilisation.objects.create(
                star_system=star,
                civilisation=civ,
                scan_level_required=scan_req,
                discovered=False,
            )
            total_civs += 1

        total_seeded += 1

    return JsonResponse({
        "status": "Seed complete.",
        "systemsSeeded": total_seeded,
        "planetsCreated": total_planets,
        "civilisationsPlaced": total_civs,
    })


# ---------------------------------------------------------------------------
# Resource Types
# ---------------------------------------------------------------------------

def _serialize_resource_type(t):
    """Return the full ResourceType payload including tuning fields."""
    return {
        "id": t.id,
        "key": t.key,
        "name": t.name,
        "color": t.color,
        "icon": t.icon,
        "order": t.order,
        "unit_label": t.unit_label,
        "unit_description": t.unit_description,
        "typical_min": t.typical_min,
        "typical_max": t.typical_max,
        "rarity_weight": t.rarity_weight,
        "scan_bracket_wide": t.scan_bracket_wide,
        "scan_bracket_narrow": t.scan_bracket_narrow,
    }


@login_required
@require_http_methods(["GET", "POST"])
def api_resource_types(request):
    """List or create resource types."""
    from .models import ResourceType

    if request.method == "GET":
        types = ResourceType.objects.all()
        return JsonResponse([_serialize_resource_type(t) for t in types], safe=False)

    if not request.user.is_superuser:
        return JsonResponse({"error": "Permission denied"}, status=403)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    t = ResourceType.objects.create(
        key=body.get("key", "").lower().replace(" ", "_"),
        name=body.get("name", ""),
        color=body.get("color", "#00ff88"),
        icon=body.get("icon", ""),
        order=body.get("order", 0),
        unit_label=body.get("unit_label", "units"),
        unit_description=body.get("unit_description", ""),
        typical_min=body.get("typical_min", 0),
        typical_max=body.get("typical_max", 100),
        rarity_weight=body.get("rarity_weight", 1.0),
        scan_bracket_wide=body.get("scan_bracket_wide", 40),
        scan_bracket_narrow=body.get("scan_bracket_narrow", 15),
    )
    return JsonResponse(_serialize_resource_type(t), status=201)


@login_required
@require_http_methods(["PUT", "DELETE"])
def api_resource_type_detail(request, pk):
    """Update or delete a resource type."""
    from .models import ResourceType
    if not request.user.is_superuser:
        return JsonResponse({"error": "Permission denied"}, status=403)

    t = get_object_or_404(ResourceType, pk=pk)
    if request.method == "DELETE":
        t.delete()
        return JsonResponse({"ok": True})

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    # Core fields
    for field in ("name", "color", "icon", "order", "key",
                  "unit_label", "unit_description"):
        if field in body:
            setattr(t, field, body[field])
    # Numeric fields — coerce so the client can send strings from <input>
    for field in ("typical_min", "typical_max",
                  "scan_bracket_wide", "scan_bracket_narrow"):
        if field in body:
            try:
                setattr(t, field, int(body[field]))
            except (TypeError, ValueError):
                return JsonResponse({"error": f"{field} must be an integer"}, status=400)
    if "rarity_weight" in body:
        try:
            t.rarity_weight = float(body["rarity_weight"])
        except (TypeError, ValueError):
            return JsonResponse({"error": "rarity_weight must be a number"}, status=400)

    t.save()
    return JsonResponse(_serialize_resource_type(t))


# ---------------------------------------------------------------------------
# Civilisations
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["GET", "POST"])
def api_civilisations(request):
    """List or create civilisations."""
    from .models import Civilisation

    if request.method == "GET":
        civs = Civilisation.objects.all()
        if not request.user.is_staff:
            civs = civs.filter(is_hidden=False)
        data = [
            {"id": c.id, "name": c.name, "description": c.description,
             "techLevel": c.tech_level, "disposition": c.disposition,
             "portraitUrl": c.portrait_url, "isHidden": c.is_hidden}
            for c in civs
        ]
        return JsonResponse(data, safe=False)

    if not request.user.is_superuser:
        return JsonResponse({"error": "Permission denied"}, status=403)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    c = Civilisation.objects.create(
        name=body.get("name", ""),
        description=body.get("description", ""),
        tech_level=body.get("techLevel", "type_0"),
        disposition=body.get("disposition", "unknown"),
        portrait_url=body.get("portraitUrl", ""),
        is_hidden=body.get("isHidden", True),
    )
    return JsonResponse({"id": c.id, "name": c.name, "techLevel": c.tech_level, "disposition": c.disposition, "isHidden": c.is_hidden}, status=201)


@login_required
@require_http_methods(["PUT", "DELETE"])
def api_civilisation_detail(request, pk):
    """Update or delete a civilisation."""
    from .models import Civilisation
    if not request.user.is_superuser:
        return JsonResponse({"error": "Permission denied"}, status=403)

    c = get_object_or_404(Civilisation, pk=pk)
    if request.method == "DELETE":
        c.delete()
        return JsonResponse({"ok": True})

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    if "name" in body: c.name = body["name"]
    if "description" in body: c.description = body["description"]
    if "techLevel" in body: c.tech_level = body["techLevel"]
    if "disposition" in body: c.disposition = body["disposition"]
    if "portraitUrl" in body: c.portrait_url = body["portraitUrl"]
    if "isHidden" in body: c.is_hidden = body["isHidden"]
    c.save()
    return JsonResponse({"id": c.id, "name": c.name, "techLevel": c.tech_level, "disposition": c.disposition, "isHidden": c.is_hidden})


# ---------------------------------------------------------------------------
# Star System Civilisations
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["GET", "POST"])
def api_system_civilisations(request, pk):
    """List or assign civilisations on a star system."""
    from .models import StarSystemCivilisation, Civilisation
    star = get_object_or_404(StarSystem, pk=pk)

    if request.method == "GET":
        links = star.civilisations.select_related("civilisation", "discovered_by").all()
        if not request.user.is_staff:
            links = links.filter(discovered=True, civilisation__is_hidden=False)
        data = [
            {"id": l.id, "civilisationId": l.civilisation_id, "name": l.civilisation.name,
             "techLevel": l.civilisation.tech_level, "disposition": l.civilisation.disposition,
             "populationEstimate": l.population_estimate, "notes": l.notes,
             "discovered": l.discovered, "scanLevelRequired": l.scan_level_required,
             "discoveredBy": l.discovered_by.name if l.discovered_by else None}
            for l in links
        ]
        return JsonResponse(data, safe=False)

    if not request.user.is_superuser:
        return JsonResponse({"error": "Permission denied"}, status=403)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    civ = get_object_or_404(Civilisation, pk=body.get("civilisationId"))
    link, created = StarSystemCivilisation.objects.get_or_create(
        star_system=star, civilisation=civ,
        defaults={
            "population_estimate": body.get("populationEstimate", ""),
            "notes": body.get("notes", ""),
            "scan_level_required": body.get("scanLevelRequired", 2),
            "discovered": body.get("discovered", False),
        },
    )
    return JsonResponse({"id": link.id, "name": civ.name, "created": created}, status=201 if created else 200)


@login_required
@require_http_methods(["DELETE"])
def api_system_civilisation_detail(request, pk, civ_pk):
    """Remove a civilisation from a star system."""
    from .models import StarSystemCivilisation
    if not request.user.is_superuser:
        return JsonResponse({"error": "Permission denied"}, status=403)
    link = get_object_or_404(StarSystemCivilisation, pk=civ_pk, star_system_id=pk)
    link.delete()
    return JsonResponse({"ok": True})


# ---------------------------------------------------------------------------
# Planets
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["GET", "POST"])
def api_system_planets(request, pk):
    """List or add planets of interest on a star system."""
    from .models import Planet
    star = get_object_or_404(StarSystem, pk=pk)

    if request.method == "GET":
        planets = star.planets_of_interest.all()
        if not request.user.is_staff:
            planets = planets.filter(discovered=True, is_hidden=False)
        data = [
            {
                "id": p.id, "name": p.name, "orbitalPosition": p.orbital_position,
                "planetType": p.planet_type, "atmosphere": p.atmosphere,
                "atmosphereDetails": p.atmosphere_details,
                "lifeType": p.life_type, "lifeDetails": p.life_details,
                "temperatureRange": p.temperature_range, "gravity": p.gravity,
                "water": p.water, "habitable": p.habitable,
                "resources": p.resources, "notes": p.notes,
                "isHidden": p.is_hidden, "discovered": p.discovered,
                "scanLevelRequired": p.scan_level_required,
                "discoveredBy": p.discovered_by.name if p.discovered_by else None,
            }
            for p in planets
        ]
        return JsonResponse(data, safe=False)

    if not request.user.is_superuser:
        return JsonResponse({"error": "Permission denied"}, status=403)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    p = Planet.objects.create(
        star_system=star,
        name=body.get("name", ""),
        orbital_position=body.get("orbitalPosition", 1),
        planet_type=body.get("planetType", "terrestrial"),
        atmosphere=body.get("atmosphere", "unknown"),
        atmosphere_details=body.get("atmosphereDetails", ""),
        life_type=body.get("lifeType", "none"),
        life_details=body.get("lifeDetails", ""),
        temperature_range=body.get("temperatureRange", ""),
        gravity=body.get("gravity", ""),
        water=body.get("water", False),
        habitable=body.get("habitable", False),
        resources=body.get("resources", {}),
        notes=body.get("notes", ""),
        is_hidden=body.get("isHidden", True),
        scan_level_required=body.get("scanLevelRequired", 1),
        discovered=body.get("discovered", False),
    )
    return JsonResponse({"id": p.id, "name": p.name}, status=201)


@login_required
@require_http_methods(["PUT", "DELETE"])
def api_system_planet_detail(request, pk, planet_pk):
    """Update or delete a planet."""
    from .models import Planet
    if not request.user.is_superuser:
        return JsonResponse({"error": "Permission denied"}, status=403)

    planet = get_object_or_404(Planet, pk=planet_pk, star_system_id=pk)
    if request.method == "DELETE":
        planet.delete()
        return JsonResponse({"ok": True})

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    field_map = {
        "name": "name", "orbitalPosition": "orbital_position",
        "planetType": "planet_type", "atmosphere": "atmosphere",
        "atmosphereDetails": "atmosphere_details",
        "lifeType": "life_type", "lifeDetails": "life_details",
        "temperatureRange": "temperature_range", "gravity": "gravity",
        "water": "water", "habitable": "habitable",
        "resources": "resources", "notes": "notes",
        "isHidden": "is_hidden", "discovered": "discovered",
        "scanLevelRequired": "scan_level_required",
    }
    for js_key, db_field in field_map.items():
        if js_key in body:
            setattr(planet, db_field, body[js_key])
    planet.save()
    return JsonResponse({"id": planet.id, "name": planet.name})


# ---------------------------------------------------------------------------
# City Maps
# ---------------------------------------------------------------------------

def _geocode(query):
    """Geocode a city name to lat/lng using Nominatim."""
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
        "q": query, "format": "json", "limit": 1,
    })
    req = urllib.request.Request(url, headers={"User-Agent": "ExodusRPG/1.0"})
    resp = urllib.request.urlopen(req, timeout=10)
    data = json.loads(resp.read().decode())
    if data:
        return float(data[0]["lat"]), float(data[0]["lon"]), data[0].get("display_name", query)
    return None, None, None


@login_required
def citymap_page(request, pk):
    """City map page with Leaflet.js."""
    from .models import CityMap
    city = get_object_or_404(CityMap, pk=pk)
    if not request.user.is_staff and not city.visible_to_players:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("ACCESS DENIED.")
    return render(request, "starmap/citymap.html", {"city": city})


@login_required
@require_http_methods(["GET", "POST"])
def api_citymap_list(request):
    """List or create city maps."""
    from .models import CityMap

    if request.method == "GET":
        if request.user.is_staff:
            cities = CityMap.objects.all()
        else:
            cities = CityMap.objects.filter(enabled=True, visible_to_players=True)
        data = [
            {
                "id": c.id, "name": c.name, "latitude": c.latitude,
                "longitude": c.longitude, "zoom": c.zoom,
                "enabled": c.enabled, "visibleToPlayers": c.visible_to_players,
            }
            for c in cities
        ]
        return JsonResponse(data, safe=False)

    # POST — create (superuser only, geocodes city name)
    if not request.user.is_superuser:
        return JsonResponse({"error": "Permission denied"}, status=403)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    query = body.get("query", "").strip()
    if not query:
        return JsonResponse({"error": "Search query required."}, status=400)

    lat, lng, display_name = _geocode(query)
    if lat is None:
        return JsonResponse({"error": f"Could not find: {query}"}, status=404)

    city = CityMap.objects.create(
        name=body.get("name", display_name.split(",")[0]),
        search_query=query,
        latitude=lat,
        longitude=lng,
        zoom=body.get("zoom", 13),
    )
    return JsonResponse({
        "id": city.id, "name": city.name, "latitude": city.latitude,
        "longitude": city.longitude, "zoom": city.zoom,
        "enabled": city.enabled, "visibleToPlayers": city.visible_to_players,
        "displayName": display_name,
    }, status=201)


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
def api_citymap_detail(request, pk):
    """Get, update, or delete a city map."""
    from .models import CityMap
    city = get_object_or_404(CityMap, pk=pk)

    if request.method == "GET":
        markers = city.markers.all()
        if not request.user.is_staff:
            markers = markers.filter(visible_to_players=True)
        data = {
            "id": city.id, "name": city.name, "latitude": city.latitude,
            "longitude": city.longitude, "zoom": city.zoom,
            "enabled": city.enabled, "visibleToPlayers": city.visible_to_players,
            "markers": [
                {
                    "id": m.id, "label": m.label, "description": m.description,
                    "latitude": m.latitude, "longitude": m.longitude,
                    "markerType": m.marker_type, "color": m.color,
                    "icon": m.icon, "visibleToPlayers": m.visible_to_players,
                    "portraitUrl": m.portrait_url,
                }
                for m in markers
            ],
        }
        return JsonResponse(data)

    if not request.user.is_superuser:
        return JsonResponse({"error": "Permission denied"}, status=403)

    if request.method == "DELETE":
        city.delete()
        return JsonResponse({"ok": True})

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    if "name" in body:
        city.name = body["name"]
    if "zoom" in body:
        city.zoom = body["zoom"]
    if "enabled" in body:
        city.enabled = body["enabled"]
    if "visibleToPlayers" in body:
        city.visible_to_players = body["visibleToPlayers"]
    city.save()
    return JsonResponse({
        "id": city.id, "name": city.name, "enabled": city.enabled,
        "visibleToPlayers": city.visible_to_players,
    })


@login_required
@require_http_methods(["POST"])
def api_citymap_marker_create(request, pk):
    """Add a marker to a city map."""
    from .models import CityMap, CityMapMarker
    if not request.user.is_superuser:
        return JsonResponse({"error": "Permission denied"}, status=403)

    city = get_object_or_404(CityMap, pk=pk)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    marker = CityMapMarker.objects.create(
        city_map=city,
        label=body.get("label", "Marker"),
        description=body.get("description", ""),
        latitude=body.get("latitude", city.latitude),
        longitude=body.get("longitude", city.longitude),
        marker_type=body.get("markerType", "custom"),
        color=body.get("color", "#00ff88"),
        icon=body.get("icon", ""),
        visible_to_players=body.get("visibleToPlayers", True),
        linked_base_id=body.get("linkedBaseId"),
        linked_character_id=body.get("linkedCharacterId"),
        portrait_url=body.get("portraitUrl", ""),
    )
    return JsonResponse({
        "id": marker.id, "label": marker.label, "latitude": marker.latitude,
        "longitude": marker.longitude, "markerType": marker.marker_type,
        "color": marker.color,
    }, status=201)


@login_required
@require_http_methods(["PUT", "DELETE"])
def api_citymap_marker_detail(request, pk, marker_pk):
    """Update or delete a marker."""
    from .models import CityMapMarker
    if not request.user.is_superuser:
        return JsonResponse({"error": "Permission denied"}, status=403)

    marker = get_object_or_404(CityMapMarker, pk=marker_pk, city_map_id=pk)

    if request.method == "DELETE":
        marker.delete()
        return JsonResponse({"ok": True})

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    for field in ["label", "description", "marker_type", "color", "icon"]:
        camel = field.replace("_t", "T").replace("_b", "B").replace("_i", "I")
        if camel in body:
            setattr(marker, field, body[camel])
    if "latitude" in body:
        marker.latitude = body["latitude"]
    if "longitude" in body:
        marker.longitude = body["longitude"]
    if "visibleToPlayers" in body:
        marker.visible_to_players = body["visibleToPlayers"]
    marker.save()
    return JsonResponse({
        "id": marker.id, "label": marker.label, "latitude": marker.latitude,
        "longitude": marker.longitude, "markerType": marker.marker_type,
        "color": marker.color,
    })
