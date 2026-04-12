"""Views for the starships application — Release B catalogues.

Ships the two superuser-facing catalogues (ShipType + ShipModule) as
JSON CRUD endpoints. The settings UI in templates/site_settings.html
talks to these. Releases C–F add class/fleet/instance endpoints.
"""

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from .models import ShipModule, ShipType


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
        "provides_sublight": m.provides_sublight,
        "provides_ftl": m.provides_ftl,
        "min_hull_size": m.min_hull_size,
        "restricted_to_types": m.restricted_to_types or [],
        "build_cost_xp_delta": m.build_cost_xp_delta,
        "xp_cost": m.xp_cost,
        "order": m.order,
    }


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

INT_FIELDS_SHIP_TYPE = (
    "default_slot_budget", "min_size", "max_size",
    "base_crew", "base_energy", "base_maintenance", "order",
)

INT_FIELDS_SHIP_MODULE = (
    "slot_cost", "crew_delta", "energy_delta", "maintenance_delta",
    "min_hull_size", "build_cost_xp_delta", "xp_cost", "order",
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
    err = _apply_int_fields(m, body, INT_FIELDS_SHIP_MODULE)
    if err:
        return err
    m.save()
    return JsonResponse(_serialize_ship_module(m))
