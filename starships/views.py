"""Views for the starships application.

Release B shipped the ShipType + ShipModule settings catalogues.
Release C adds the StarshipClass editor: class CRUD, module install
endpoints, derived-stat computation, and the /starships/ page view.
"""

import json

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_http_methods

from .models import (
    ClassModule,
    Fleet,
    ShipModule,
    ShipModuleSection,
    ShipType,
    Starship,
    StarshipClass,
)


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------

def _serialize_ship_type(t):
    return {
        "id": t.id,
        "key": t.key,
        "name": t.name,
        "description": t.description,
        "default_slot_budget": t.default_slot_budget,
        "min_size": t.min_size,
        "max_size": t.max_size,
        "base_crew": t.base_crew,
        "base_energy": t.base_energy,
        "base_maintenance": t.base_maintenance,
        "initiative_bonus": t.initiative_bonus,
        "base_health": t.base_health,
        "base_speed": t.base_speed,
        "base_defense": t.base_defense,
        "base_armor": t.base_armor,
        "base_scanning": t.base_scanning,
        "base_shield": t.base_shield,
        "base_battery_power": t.base_battery_power,
        "order": t.order,
    }


def _serialize_ship_module(m):
    return {
        "id": m.id,
        "key": m.key,
        "name": m.name,
        "description": m.description,
        "category": m.category,
        "category_label": m.get_category_display(),
        "slot_cost": m.slot_cost,
        "crew_delta": m.crew_delta,
        "energy_delta": m.energy_delta,
        "maintenance_delta": m.maintenance_delta,
        "health_delta": m.health_delta,
        "speed_delta": m.speed_delta,
        "defense_delta": m.defense_delta,
        "armor_delta": m.armor_delta,
        "scanning_delta": m.scanning_delta,
        "shield_delta": m.shield_delta,
        "battery_delta": m.battery_delta,
        "battery_cost": m.battery_cost,
        "weapon_damage": m.weapon_damage,
        "weapon_range": m.weapon_range,
        "weapon_min_range": m.weapon_min_range,
        "weapon_size_bias": m.weapon_size_bias,
        "weapon_travel_turns": m.weapon_travel_turns,
        "provides_sublight": m.provides_sublight,
        "provides_ftl": m.provides_ftl,
        "min_hull_size": m.min_hull_size,
        "restricted_to_types": m.restricted_to_types or [],
        "build_cost_xp_delta": m.build_cost_xp_delta,
        "xp_cost": m.xp_cost,
        "section_id": m.section_id,
        "section_key": m.section.key if m.section else None,
        "section_name": m.section.name if m.section else None,
        "level": m.level,
        "order": m.order,
    }


def _serialize_ship_module_section(s):
    return {
        "id": s.id,
        "key": s.key,
        "name": s.name,
        "description": s.description,
        "order": s.order,
    }


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

INT_FIELDS_SHIP_TYPE = (
    "default_slot_budget", "min_size", "max_size",
    "base_crew", "base_energy", "base_maintenance",
    "initiative_bonus",
    "base_health", "base_speed", "base_defense", "base_armor", "base_scanning",
    "base_shield", "base_battery_power",
    "order",
)

INT_FIELDS_SHIP_MODULE = (
    "slot_cost", "crew_delta", "energy_delta", "maintenance_delta",
    "health_delta", "speed_delta", "defense_delta", "armor_delta", "scanning_delta",
    "shield_delta", "battery_delta", "battery_cost",
    "weapon_damage", "weapon_range", "weapon_min_range",
    "weapon_size_bias", "weapon_travel_turns",
    "min_hull_size", "build_cost_xp_delta", "xp_cost", "level", "order",
)


def _apply_int_fields(obj, body, fields):
    """Copy integer fields from body into obj, coercing and validating."""
    for field in fields:
        if field in body:
            try:
                setattr(obj, field, int(body[field]))
            except (TypeError, ValueError):
                return JsonResponse(
                    {"error": f"{field} must be an integer"}, status=400,
                )
    return None


# ---------------------------------------------------------------------------
# Ship Types
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["GET", "POST"])
def api_ship_types(request):
    """List or create ShipType rows."""
    if request.method == "GET":
        return JsonResponse(
            [_serialize_ship_type(t) for t in ShipType.objects.all()],
            safe=False,
        )

    if not request.user.is_superuser:
        return JsonResponse({"error": "Permission denied"}, status=403)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    key = (body.get("key") or "").lower().strip().replace(" ", "_")
    name = (body.get("name") or "").strip()
    if not key or not name:
        return JsonResponse({"error": "key and name required"}, status=400)

    t = ShipType(key=key, name=name, description=body.get("description", ""))
    err = _apply_int_fields(t, body, INT_FIELDS_SHIP_TYPE)
    if err:
        return err
    t.save()
    return JsonResponse(_serialize_ship_type(t), status=201)


@login_required
@require_http_methods(["PUT", "DELETE"])
def api_ship_type_detail(request, pk):
    if not request.user.is_superuser:
        return JsonResponse({"error": "Permission denied"}, status=403)

    t = get_object_or_404(ShipType, pk=pk)
    if request.method == "DELETE":
        t.delete()
        return JsonResponse({"ok": True})

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    for field in ("key", "name", "description"):
        if field in body:
            setattr(t, field, body[field])
    err = _apply_int_fields(t, body, INT_FIELDS_SHIP_TYPE)
    if err:
        return err
    t.save()
    return JsonResponse(_serialize_ship_type(t))


# ---------------------------------------------------------------------------
# Ship Modules
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["GET", "POST"])
def api_ship_modules(request):
    """List or create ShipModule rows."""
    if request.method == "GET":
        return JsonResponse(
            [_serialize_ship_module(m) for m in ShipModule.objects.all()],
            safe=False,
        )

    if not request.user.is_superuser:
        return JsonResponse({"error": "Permission denied"}, status=403)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    key = (body.get("key") or "").lower().strip().replace(" ", "_")
    name = (body.get("name") or "").strip()
    if not key or not name:
        return JsonResponse({"error": "key and name required"}, status=400)

    m = ShipModule(
        key=key,
        name=name,
        description=body.get("description", ""),
        category=body.get("category", "special"),
        provides_sublight=bool(body.get("provides_sublight", False)),
        provides_ftl=bool(body.get("provides_ftl", False)),
        restricted_to_types=body.get("restricted_to_types") or [],
    )
    section_id = body.get("section_id")
    if section_id:
        try:
            m.section = ShipModuleSection.objects.get(pk=section_id)
        except ShipModuleSection.DoesNotExist:
            return JsonResponse({"error": "section_id not found"}, status=400)
    err = _apply_int_fields(m, body, INT_FIELDS_SHIP_MODULE)
    if err:
        return err
    m.save()
    return JsonResponse(_serialize_ship_module(m), status=201)


@login_required
@require_http_methods(["PUT", "DELETE"])
def api_ship_module_detail(request, pk):
    if not request.user.is_superuser:
        return JsonResponse({"error": "Permission denied"}, status=403)

    m = get_object_or_404(ShipModule, pk=pk)
    if request.method == "DELETE":
        m.delete()
        return JsonResponse({"ok": True})

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    for field in ("key", "name", "description", "category"):
        if field in body:
            setattr(m, field, body[field])
    if "provides_sublight" in body:
        m.provides_sublight = bool(body["provides_sublight"])
    if "provides_ftl" in body:
        m.provides_ftl = bool(body["provides_ftl"])
    if "restricted_to_types" in body:
        val = body["restricted_to_types"]
        if isinstance(val, str):
            # Accept comma-separated string from a plain text input.
            val = [v.strip() for v in val.split(",") if v.strip()]
        if not isinstance(val, list):
            return JsonResponse(
                {"error": "restricted_to_types must be a list"}, status=400,
            )
        m.restricted_to_types = val
    if "section_id" in body:
        if body["section_id"] in (None, "", 0):
            m.section = None
        else:
            try:
                m.section = ShipModuleSection.objects.get(pk=body["section_id"])
            except ShipModuleSection.DoesNotExist:
                return JsonResponse({"error": "section_id not found"}, status=400)
    err = _apply_int_fields(m, body, INT_FIELDS_SHIP_MODULE)
    if err:
        return err
    m.save()
    return JsonResponse(_serialize_ship_module(m))


# ---------------------------------------------------------------------------
# Ship Module Sections
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["GET", "POST"])
def api_ship_module_sections(request):
    if request.method == "GET":
        return JsonResponse(
            [_serialize_ship_module_section(s) for s in ShipModuleSection.objects.all()],
            safe=False,
        )
    if not request.user.is_superuser:
        return JsonResponse({"error": "Permission denied"}, status=403)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    key = (body.get("key") or "").lower().strip().replace(" ", "_")
    name = (body.get("name") or "").strip()
    if not key or not name:
        return JsonResponse({"error": "key and name required"}, status=400)
    section = ShipModuleSection.objects.create(
        key=key, name=name,
        description=body.get("description", ""),
        order=int(body.get("order", 0) or 0),
    )
    return JsonResponse(_serialize_ship_module_section(section), status=201)


@login_required
@require_http_methods(["PUT", "DELETE"])
def api_ship_module_section_detail(request, pk):
    if not request.user.is_superuser:
        return JsonResponse({"error": "Permission denied"}, status=403)
    section = get_object_or_404(ShipModuleSection, pk=pk)
    if request.method == "DELETE":
        section.delete()
        return JsonResponse({"ok": True})
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    for field in ("key", "name", "description"):
        if field in body:
            setattr(section, field, body[field])
    if "order" in body:
        try:
            section.order = int(body["order"])
        except (TypeError, ValueError):
            return JsonResponse({"error": "order must be an integer"}, status=400)
    section.save()
    return JsonResponse(_serialize_ship_module_section(section))


# ---------------------------------------------------------------------------
# Starship classes — derived stats + CRUD
# ---------------------------------------------------------------------------

def _user_agency(user):
    """Resolve a player's agency via character workspace assignment."""
    # Reuse the starmap helper so the behaviour is identical across apps.
    from starmap.views import _get_user_agency
    return _get_user_agency(user)


def _visible_classes(user):
    """QuerySet of classes the user may view.

    Superusers see everything. Players see shared classes (created_by
    null) plus classes owned by their own agency.
    """
    qs = StarshipClass.objects.select_related("ship_type", "created_by")
    if user.is_superuser:
        return qs
    agency = _user_agency(user)
    if agency is None:
        return qs.filter(created_by__isnull=True)
    from django.db.models import Q
    return qs.filter(Q(created_by__isnull=True) | Q(created_by=agency))


def _can_edit_class(user, cls):
    """Write permission: superuser always, agency owner for their own classes."""
    if user.is_superuser:
        return True
    if cls.is_locked:
        return False
    if cls.created_by_id is None:
        return False  # shared classes are GM-owned
    agency = _user_agency(user)
    return agency is not None and agency.id == cls.created_by_id


def compute_class_stats(cls):
    """Compute derived stats + warnings for a StarshipClass.

    Everything is summed off the installed ClassModules so the UI can
    show live totals without duplicating logic in JavaScript.
    """
    from exodus.models import SiteSettings
    enforce = SiteSettings.load().enforce_ship_slot_budget

    ship_type = cls.ship_type
    class_modules = (
        cls.class_modules
        .select_related("module")
        .order_by("position", "id")
    )

    slot_budget = ship_type.default_slot_budget
    slots_used = 0
    required_crew = ship_type.base_crew
    energy = ship_type.base_energy
    maintenance = ship_type.base_maintenance
    health = ship_type.base_health
    speed = ship_type.base_speed
    defense = ship_type.base_defense
    armor = ship_type.base_armor
    scanning = ship_type.base_scanning
    shield = ship_type.base_shield
    battery_power = ship_type.base_battery_power
    initiative_bonus = ship_type.initiative_bonus
    arsenal = []  # list of weapon-module summaries for the editor/UI
    has_sublight = False
    has_ftl = False
    has_power = False
    build_cost_total = cls.build_cost_xp

    for cm in class_modules:
        qty = max(0, cm.quantity or 0)
        m = cm.module
        slots_used += m.slot_cost * qty
        required_crew += m.crew_delta * qty
        energy += m.energy_delta * qty
        maintenance += m.maintenance_delta * qty
        health += m.health_delta * qty
        speed += m.speed_delta * qty
        defense += m.defense_delta * qty
        armor += m.armor_delta * qty
        scanning += m.scanning_delta * qty
        shield += m.shield_delta * qty
        battery_power += m.battery_delta * qty
        if m.weapon_damage > 0 and qty > 0:
            arsenal.append({
                "module_id": m.id,
                "module_key": m.key,
                "name": m.name,
                "quantity": qty,
                "damage": m.weapon_damage,
                "range": m.weapon_range,
                "min_range": m.weapon_min_range,
                "size_bias": m.weapon_size_bias,
                "travel_turns": m.weapon_travel_turns,
                "battery_cost": m.battery_cost,
                "category": m.category,
                "section_key": m.section.key if m.section else None,
                "section_name": m.section.name if m.section else None,
                "level": m.level,
            })
        build_cost_total += m.build_cost_xp_delta * qty
        if m.provides_sublight and qty > 0:
            has_sublight = True
        if m.provides_ftl and qty > 0:
            has_ftl = True
        if m.category == "power" and qty > 0:
            has_power = True

    # Floor combat stats at zero — modules can nudge them negative
    # but a ship with speed 0 just can't move; it doesn't go backwards.
    speed = max(0, speed)
    defense = max(0, defense)
    armor = max(0, armor)
    health = max(1, health)
    scanning = max(0, scanning)
    shield = max(0, shield)
    battery_power = max(0, battery_power)

    warnings = []

    if slots_used > slot_budget:
        warnings.append({
            "severity": "error" if enforce else "warn",
            "code": "over_budget",
            "message": f"Over slot budget ({slots_used}/{slot_budget}).",
        })

    if not has_sublight:
        warnings.append({
            "severity": "warn",
            "code": "no_sublight",
            "message": "No sublight drive — cannot manoeuvre.",
        })

    if ship_type.key != "drone" and not has_ftl:
        warnings.append({
            "severity": "info",
            "code": "no_ftl",
            "message": "No FTL drive — cannot jump systems.",
        })

    if not has_power and energy > 0:
        warnings.append({
            "severity": "warn",
            "code": "no_power",
            "message": "No power source — modules have no energy to draw.",
        })

    if cls.size < ship_type.min_size or cls.size > ship_type.max_size:
        warnings.append({
            "severity": "error" if enforce else "warn",
            "code": "bad_size",
            "message": (
                f"Size {cls.size} out of range for {ship_type.name} "
                f"({ship_type.min_size}-{ship_type.max_size})."
            ),
        })

    # Modules restricted to other ship types
    wrong_type = []
    for cm in class_modules:
        allowed = cm.module.restricted_to_types or []
        if allowed and ship_type.key not in allowed:
            wrong_type.append(cm.module.name)
    if wrong_type:
        warnings.append({
            "severity": "error" if enforce else "warn",
            "code": "wrong_type",
            "message": "Modules not allowed on this ship type: " + ", ".join(wrong_type),
        })

    # Modules below min hull size
    too_big_for_hull = [
        cm.module.name for cm in class_modules
        if cm.module.min_hull_size > cls.size
    ]
    if too_big_for_hull:
        warnings.append({
            "severity": "warn",
            "code": "hull_too_small",
            "message": "Hull too small for: " + ", ".join(too_big_for_hull),
        })

    return {
        "slot_budget": slot_budget,
        "slots_used": slots_used,
        "slots_free": slot_budget - slots_used,
        "required_crew": required_crew,
        "energy": energy,
        "maintenance": maintenance,
        "health": health,
        "speed": speed,
        "defense": defense,
        "armor": armor,
        "scanning": scanning,
        "shield": shield,
        "battery_power": battery_power,
        "arsenal": arsenal,
        "initiative_bonus": initiative_bonus,
        "size": cls.size,
        "has_sublight": has_sublight,
        "has_ftl": has_ftl,
        "has_power": has_power,
        "build_cost_xp_total": build_cost_total,
        "enforce_slot_budget": enforce,
        "warnings": warnings,
    }


def _serialize_class_module(cm):
    m = cm.module
    return {
        "id": cm.id,
        "module_id": cm.module_id,
        "module_key": m.key,
        "module_name": m.name,
        "module_category": m.category,
        "module_category_label": m.get_category_display(),
        "slot_cost": m.slot_cost,
        "crew_delta": m.crew_delta,
        "energy_delta": m.energy_delta,
        "maintenance_delta": m.maintenance_delta,
        "provides_sublight": m.provides_sublight,
        "provides_ftl": m.provides_ftl,
        "build_cost_xp_delta": m.build_cost_xp_delta,
        "section_id": m.section_id,
        "section_key": m.section.key if m.section else None,
        "section_name": m.section.name if m.section else None,
        "level": m.level,
        "quantity": cm.quantity,
        "notes": cm.notes,
        "position": cm.position,
    }


def _serialize_class(cls, include_modules=True, include_stats=True):
    data = {
        "id": cls.id,
        "name": cls.name,
        "description": cls.description,
        "ship_type_id": cls.ship_type_id,
        "ship_type_key": cls.ship_type.key,
        "ship_type_name": cls.ship_type.name,
        "size": cls.size,
        "is_locked": cls.is_locked,
        "build_cost_xp": cls.build_cost_xp,
        "build_required_successes": cls.build_required_successes,
        "created_by_id": cls.created_by_id,
        "created_by_name": cls.created_by.name if cls.created_by else None,
        "is_shared": cls.created_by_id is None,
        "created_at": cls.created_at.isoformat() if cls.created_at else None,
        "updated_at": cls.updated_at.isoformat() if cls.updated_at else None,
    }
    if include_modules:
        data["modules"] = [
            _serialize_class_module(cm)
            for cm in cls.class_modules.select_related("module").order_by("position", "id")
        ]
    if include_stats:
        data["stats"] = compute_class_stats(cls)
    return data


@login_required
@require_http_methods(["GET", "POST"])
def api_classes(request):
    """List visible classes, or create a new one."""
    if request.method == "GET":
        qs = _visible_classes(request.user).order_by("name")
        return JsonResponse(
            [_serialize_class(c, include_modules=False) for c in qs],
            safe=False,
        )

    # POST — create
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    name = (body.get("name") or "").strip()
    if not name:
        return JsonResponse({"error": "name required"}, status=400)

    ship_type_id = body.get("ship_type_id")
    if not ship_type_id:
        return JsonResponse({"error": "ship_type_id required"}, status=400)
    try:
        ship_type = ShipType.objects.get(pk=ship_type_id)
    except ShipType.DoesNotExist:
        return JsonResponse({"error": "ship_type_id not found"}, status=400)

    is_shared = bool(body.get("is_shared", False))
    if is_shared and not request.user.is_superuser:
        return JsonResponse(
            {"error": "Only GMs can create shared classes"}, status=403,
        )
    # Owner resolution:
    #   - is_shared=True       → created_by null (GM-shared)
    #   - GM + created_by_agency_id → that specific agency
    #   - otherwise             → user's own agency
    owner = None
    if not is_shared:
        override = body.get("created_by_agency_id")
        if override and request.user.is_superuser:
            from agencies.models import Agency
            try:
                owner = Agency.objects.get(pk=override)
            except Agency.DoesNotExist:
                return JsonResponse({"error": "created_by_agency_id not found"}, status=400)
        else:
            owner = _user_agency(request.user)
        if owner is None:
            return JsonResponse(
                {"error": "No agency found for user — cannot own a class"}, status=400,
            )

    cls = StarshipClass(
        name=name,
        ship_type=ship_type,
        size=int(body.get("size", ship_type.min_size)),
        description=body.get("description", ""),
        created_by=owner,
        build_cost_xp=int(body.get("build_cost_xp", 0)),
        build_required_successes=int(body.get("build_required_successes", 5)),
    )
    cls.save()
    return JsonResponse(_serialize_class(cls), status=201)


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
def api_class_detail(request, pk):
    cls = get_object_or_404(
        StarshipClass.objects.select_related("ship_type", "created_by"),
        pk=pk,
    )

    # View permission
    if not request.user.is_superuser:
        agency = _user_agency(request.user)
        if cls.created_by_id is not None and (agency is None or agency.id != cls.created_by_id):
            return JsonResponse({"error": "Not visible"}, status=404)

    if request.method == "GET":
        return JsonResponse(_serialize_class(cls))

    if not _can_edit_class(request.user, cls):
        return JsonResponse({"error": "Permission denied"}, status=403)

    if request.method == "DELETE":
        if cls.hulls.exists():
            return JsonResponse(
                {"error": "Cannot delete: class has commissioned hulls."},
                status=400,
            )
        cls.delete()
        return JsonResponse({"ok": True})

    # PUT
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    for field in ("name", "description"):
        if field in body:
            setattr(cls, field, body[field])
    for field in ("size", "build_cost_xp", "build_required_successes"):
        if field in body:
            try:
                setattr(cls, field, int(body[field]))
            except (TypeError, ValueError):
                return JsonResponse(
                    {"error": f"{field} must be an integer"}, status=400,
                )
    if "ship_type_id" in body:
        try:
            cls.ship_type = ShipType.objects.get(pk=body["ship_type_id"])
        except ShipType.DoesNotExist:
            return JsonResponse({"error": "ship_type_id not found"}, status=400)
    if "is_locked" in body and request.user.is_superuser:
        cls.is_locked = bool(body["is_locked"])

    # Hard-enforce slot budget on save if the site setting demands it.
    cls.save()
    stats = compute_class_stats(cls)
    if stats["enforce_slot_budget"]:
        errors = [w for w in stats["warnings"] if w["severity"] == "error"]
        if errors:
            # Rollback by re-loading — we already saved, so the caller
            # can live with a successful write + blocking error. Return
            # the class with error warnings so the UI can show them.
            return JsonResponse(
                {**_serialize_class(cls), "_enforced_errors": errors},
                status=422,
            )
    return JsonResponse(_serialize_class(cls))


# ---------------------------------------------------------------------------
# ClassModule — install / remove / update
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["POST"])
def api_class_add_module(request, pk):
    cls = get_object_or_404(StarshipClass, pk=pk)
    if not _can_edit_class(request.user, cls):
        return JsonResponse({"error": "Permission denied"}, status=403)
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    module_id = body.get("module_id")
    if not module_id:
        return JsonResponse({"error": "module_id required"}, status=400)
    try:
        module = ShipModule.objects.select_related("section").get(pk=module_id)
    except ShipModule.DoesNotExist:
        return JsonResponse({"error": "module_id not found"}, status=400)

    # Sectioned modules are one-per-class: installing any tier in the
    # section atomically replaces the existing tier so upgrading a
    # Gatling Gun to a Vengeance Cannon is a single click, not a
    # remove-then-add dance.
    replaced_position = None
    if module.section_id is not None:
        existing_qs = cls.class_modules.filter(module__section_id=module.section_id)
        existing = existing_qs.first()
        if existing is not None:
            replaced_position = existing.position
            existing.delete()

    position = (
        replaced_position
        if replaced_position is not None
        else cls.class_modules.count()
    )
    cm = ClassModule.objects.create(
        starship_class=cls,
        module=module,
        quantity=max(1, int(body.get("quantity", 1))),
        notes=body.get("notes", ""),
        position=position,
    )
    return JsonResponse(_serialize_class_module(cm), status=201)


@login_required
@require_http_methods(["PUT", "DELETE"])
def api_class_module_detail(request, pk, cm_id):
    cls = get_object_or_404(StarshipClass, pk=pk)
    if not _can_edit_class(request.user, cls):
        return JsonResponse({"error": "Permission denied"}, status=403)
    cm = get_object_or_404(ClassModule, pk=cm_id, starship_class=cls)
    if request.method == "DELETE":
        cm.delete()
        # Re-pack positions so the grid stays dense.
        for i, other in enumerate(cls.class_modules.order_by("position", "id")):
            if other.position != i:
                other.position = i
                other.save(update_fields=["position"])
        return JsonResponse({"ok": True})
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    if "quantity" in body:
        try:
            cm.quantity = max(0, int(body["quantity"]))
        except (TypeError, ValueError):
            return JsonResponse({"error": "quantity must be an integer"}, status=400)
    if "notes" in body:
        cm.notes = body["notes"]
    if "position" in body:
        try:
            cm.position = int(body["position"])
        except (TypeError, ValueError):
            return JsonResponse({"error": "position must be an integer"}, status=400)
    cm.save()
    return JsonResponse(_serialize_class_module(cm))


# ---------------------------------------------------------------------------
# Standalone page
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Starship instances (Release D)
# ---------------------------------------------------------------------------

def _visible_ships(user):
    """Ships the user may see. Superuser sees everything; players see
    hulls owned by their agency."""
    qs = Starship.objects.select_related(
        "starship_class", "starship_class__ship_type", "agency",
        "fleet", "build_assigned_base", "location",
    )
    if user.is_superuser:
        return qs
    agency = _user_agency(user)
    if agency is None:
        return qs.none()
    return qs.filter(agency=agency)


def _can_edit_ship(user, ship):
    if user.is_superuser:
        return True
    agency = _user_agency(user)
    return agency is not None and agency.id == ship.agency_id


def _serialize_ship(ship):
    cls = ship.starship_class
    stats = compute_class_stats(cls)
    return {
        "id": ship.id,
        "name": ship.name,
        "hull_number": ship.hull_number,
        "status": ship.status,
        "status_label": ship.get_status_display(),
        "current_crew": ship.current_crew,
        "required_crew": stats["required_crew"],
        "maintenance_state": ship.maintenance_state,
        "current_successes": ship.current_successes,
        "build_required_successes": cls.build_required_successes,
        "starship_class_id": cls.id,
        "starship_class_name": cls.name,
        "ship_type_name": cls.ship_type.name,
        "agency_id": ship.agency_id,
        "agency_name": ship.agency.name if ship.agency else None,
        "fleet_id": ship.fleet_id,
        "fleet_name": ship.fleet.name if ship.fleet else None,
        "build_assigned_base_id": ship.build_assigned_base_id,
        "build_assigned_base_name": (
            ship.build_assigned_base.name if ship.build_assigned_base else None
        ),
        "location_id": ship.location_id,
        "location_name": ship.location.name if ship.location else None,
        "commissioned_at": ship.commissioned_at.isoformat() if ship.commissioned_at else None,
        "notes": ship.notes,
        "created_at": ship.created_at.isoformat() if ship.created_at else None,
        "updated_at": ship.updated_at.isoformat() if ship.updated_at else None,
    }


@login_required
@require_http_methods(["GET", "POST"])
def api_ships(request):
    if request.method == "GET":
        qs = _visible_ships(request.user).order_by("agency", "name")
        return JsonResponse(
            [_serialize_ship(s) for s in qs], safe=False,
        )

    # POST — build a new hull from a class
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    class_id = body.get("starship_class_id")
    if not class_id:
        return JsonResponse({"error": "starship_class_id required"}, status=400)
    try:
        cls = StarshipClass.objects.select_related("ship_type").get(pk=class_id)
    except StarshipClass.DoesNotExist:
        return JsonResponse({"error": "class not found"}, status=404)

    # Visibility check — same rules as class list
    if not request.user.is_superuser:
        agency = _user_agency(request.user)
        if cls.created_by_id is not None and (agency is None or agency.id != cls.created_by_id):
            return JsonResponse({"error": "Class not visible"}, status=403)
    else:
        agency = _user_agency(request.user)

    # Determine owning agency: explicit override (GM only) or the user's agency
    from agencies.models import Agency, Base
    agency_id = body.get("agency_id")
    if agency_id and request.user.is_superuser:
        try:
            agency = Agency.objects.get(pk=agency_id)
        except Agency.DoesNotExist:
            return JsonResponse({"error": "agency not found"}, status=400)
    if agency is None:
        return JsonResponse(
            {"error": "No owning agency resolvable for user"}, status=400,
        )

    name = (body.get("name") or "").strip()
    if not name:
        return JsonResponse({"error": "name required"}, status=400)

    ship = Starship(
        name=name,
        hull_number=body.get("hull_number", ""),
        starship_class=cls,
        agency=agency,
        status="under_construction",
    )
    # Optional base assignment (must belong to the owning agency)
    base_id = body.get("build_assigned_base_id")
    if base_id:
        try:
            base = Base.objects.get(pk=base_id, agency=agency)
            ship.build_assigned_base = base
        except Base.DoesNotExist:
            return JsonResponse(
                {"error": "base not found or not owned by agency"}, status=400,
            )
    ship.save()
    return JsonResponse(_serialize_ship(ship), status=201)


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
def api_ship_detail(request, pk):
    ship = get_object_or_404(
        Starship.objects.select_related(
            "starship_class", "starship_class__ship_type", "agency",
            "fleet", "build_assigned_base", "location",
        ),
        pk=pk,
    )

    # View permission
    if not request.user.is_superuser:
        agency = _user_agency(request.user)
        if agency is None or agency.id != ship.agency_id:
            return JsonResponse({"error": "Not visible"}, status=404)

    if request.method == "GET":
        return JsonResponse(_serialize_ship(ship))

    if not _can_edit_ship(request.user, ship):
        return JsonResponse({"error": "Permission denied"}, status=403)

    if request.method == "DELETE":
        ship.delete()
        return JsonResponse({"ok": True})

    # PUT
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    for field in ("name", "hull_number", "notes"):
        if field in body:
            setattr(ship, field, body[field])
    for field in ("current_crew", "maintenance_state", "current_successes"):
        if field in body:
            try:
                setattr(ship, field, int(body[field]))
            except (TypeError, ValueError):
                return JsonResponse({"error": f"{field} must be an integer"}, status=400)
    if "status" in body:
        valid = {k for k, _ in Starship.STATUS_CHOICES}
        if body["status"] not in valid:
            return JsonResponse({"error": "invalid status"}, status=400)
        ship.status = body["status"]
    # Location FK
    if "location_id" in body:
        if body["location_id"] in (None, "", 0):
            ship.location = None
        else:
            from starmap.models import StarSystem
            try:
                ship.location = StarSystem.objects.get(pk=body["location_id"])
            except StarSystem.DoesNotExist:
                return JsonResponse({"error": "location not found"}, status=400)
    # Fleet FK
    if "fleet_id" in body:
        if body["fleet_id"] in (None, "", 0):
            ship.fleet = None
        else:
            try:
                fleet = Fleet.objects.get(pk=body["fleet_id"])
            except Fleet.DoesNotExist:
                return JsonResponse({"error": "fleet not found"}, status=400)
            if fleet.agency_id != ship.agency_id:
                return JsonResponse(
                    {"error": "fleet must belong to the ship's agency"},
                    status=400,
                )
            ship.fleet = fleet
    # Build base FK
    if "build_assigned_base_id" in body:
        if body["build_assigned_base_id"] in (None, "", 0):
            ship.build_assigned_base = None
        else:
            from agencies.models import Base
            try:
                ship.build_assigned_base = Base.objects.get(
                    pk=body["build_assigned_base_id"], agency=ship.agency,
                )
            except Base.DoesNotExist:
                return JsonResponse(
                    {"error": "base not found or not owned by agency"}, status=400,
                )
    ship.save()
    return JsonResponse(_serialize_ship(ship))


@login_required
@require_http_methods(["POST"])
def api_ship_construction_roll(request, pk):
    """Record construction progress against an under_construction hull.

    Body: {successes: int}. Auto-promotes to active when the class's
    build_required_successes is reached and sets commissioned_at to
    the current time.
    """
    from django.utils import timezone

    ship = get_object_or_404(
        Starship.objects.select_related("starship_class"), pk=pk,
    )
    if not _can_edit_ship(request.user, ship):
        return JsonResponse({"error": "Permission denied"}, status=403)
    if ship.status != "under_construction":
        return JsonResponse(
            {"error": "Ship is not under construction"}, status=400,
        )
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    try:
        successes = int(body.get("successes", 0))
    except (TypeError, ValueError):
        return JsonResponse({"error": "successes must be an integer"}, status=400)
    if successes < 0:
        return JsonResponse({"error": "successes cannot be negative"}, status=400)

    ship.current_successes += successes
    required = ship.starship_class.build_required_successes
    completed = False
    if ship.current_successes >= required:
        ship.current_successes = required
        ship.status = "active"
        ship.commissioned_at = timezone.now()
        completed = True
    ship.save()
    return JsonResponse({
        "ship": _serialize_ship(ship),
        "completed": completed,
    })


# ---------------------------------------------------------------------------
# Fleets (Release E)
# ---------------------------------------------------------------------------

def _visible_fleets(user):
    qs = Fleet.objects.select_related("agency").prefetch_related("ships")
    if user.is_superuser:
        return qs
    agency = _user_agency(user)
    if agency is None:
        return qs.none()
    return qs.filter(agency=agency)


def _can_edit_fleet(user, fleet):
    if user.is_superuser:
        return True
    agency = _user_agency(user)
    return agency is not None and agency.id == fleet.agency_id


def _serialize_fleet(fleet, include_ships=True):
    data = {
        "id": fleet.id,
        "name": fleet.name,
        "commander": fleet.commander,
        "notes": fleet.notes,
        "agency_id": fleet.agency_id,
        "agency_name": fleet.agency.name if fleet.agency else None,
        "created_at": fleet.created_at.isoformat() if fleet.created_at else None,
    }
    if include_ships:
        data["ships"] = [_serialize_ship(s) for s in fleet.ships.all()]
        data["ship_count"] = len(data["ships"])
    else:
        data["ship_count"] = fleet.ships.count()
    return data


@login_required
@require_http_methods(["GET", "POST"])
def api_fleets(request):
    if request.method == "GET":
        qs = _visible_fleets(request.user).order_by("agency__name", "name")
        return JsonResponse(
            [_serialize_fleet(f, include_ships=False) for f in qs],
            safe=False,
        )

    # POST — create
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    name = (body.get("name") or "").strip()
    if not name:
        return JsonResponse({"error": "name required"}, status=400)

    from agencies.models import Agency
    agency = _user_agency(request.user)
    # Superusers can create a fleet for any agency via explicit agency_id
    if request.user.is_superuser and body.get("agency_id"):
        try:
            agency = Agency.objects.get(pk=body["agency_id"])
        except Agency.DoesNotExist:
            return JsonResponse({"error": "agency not found"}, status=400)
    if agency is None:
        return JsonResponse(
            {"error": "No owning agency resolvable for user"}, status=400,
        )

    fleet = Fleet.objects.create(
        name=name,
        agency=agency,
        commander=body.get("commander", ""),
        notes=body.get("notes", ""),
    )
    return JsonResponse(_serialize_fleet(fleet), status=201)


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
def api_fleet_detail(request, pk):
    fleet = get_object_or_404(
        Fleet.objects.select_related("agency").prefetch_related(
            "ships", "ships__starship_class", "ships__starship_class__ship_type",
            "ships__agency", "ships__fleet", "ships__location",
        ),
        pk=pk,
    )

    # View permission
    if not request.user.is_superuser:
        agency = _user_agency(request.user)
        if agency is None or agency.id != fleet.agency_id:
            return JsonResponse({"error": "Not visible"}, status=404)

    if request.method == "GET":
        return JsonResponse(_serialize_fleet(fleet))

    if not _can_edit_fleet(request.user, fleet):
        return JsonResponse({"error": "Permission denied"}, status=403)

    if request.method == "DELETE":
        # Null out ship fleet assignments first so the cascade doesn't
        # nuke the hulls along with the fleet.
        fleet.ships.update(fleet=None)
        fleet.delete()
        return JsonResponse({"ok": True})

    # PUT
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    for field in ("name", "commander", "notes"):
        if field in body:
            setattr(fleet, field, body[field])
    fleet.save()
    return JsonResponse(_serialize_fleet(fleet))


# ---------------------------------------------------------------------------
# Legacy fleet import (Release F)
# ---------------------------------------------------------------------------

@login_required
@require_GET
def api_legacy_status(request):
    """Tell the settings UI how many legacy fleet entries are pending."""
    if not request.user.is_superuser:
        return JsonResponse({"error": "Permission denied"}, status=403)
    from .legacy_import import legacy_status
    return JsonResponse(legacy_status())


@login_required
@require_http_methods(["POST"])
def api_legacy_import(request):
    """Run the legacy fleet importer for all agencies (or one)."""
    if not request.user.is_superuser:
        return JsonResponse({"error": "Permission denied"}, status=403)
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    from .legacy_import import import_all_legacy_fleets
    result = import_all_legacy_fleets(
        dry_run=bool(body.get("dry_run", False)),
        force=bool(body.get("force", False)),
        agency_id=body.get("agency_id"),
    )
    return JsonResponse(result)


# ---------------------------------------------------------------------------
# Standalone page
# ---------------------------------------------------------------------------

@login_required
@require_GET
def starships_page(request):
    """Standalone starships hub — classes, ships, and fleets.

    Staff always see it; players only when SiteSettings.show_starships
    is toggled on from Settings > Map Visibility.
    """
    if not request.user.is_staff:
        from exodus.models import SiteSettings
        settings_obj = SiteSettings.load()
        if not settings_obj.show_starships:
            return HttpResponseForbidden("STARSHIPS ACCESS DISABLED")
    return render(request, "starships/page.html", {
        "is_superuser": request.user.is_superuser,
    })
