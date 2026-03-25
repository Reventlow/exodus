"""Core views for Exodus site settings."""

import json
from pathlib import Path

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from .models import MeritDefinition, PullingString, SiteSettings


@staff_member_required
def site_settings(request):
    """Allow staff to update site-wide settings."""
    settings_obj = SiteSettings.load()

    if request.method == "POST":
        date_value = request.POST.get("next_game_date", "").strip()
        settings_obj.next_game_date = date_value or None
        settings_obj.charter_text = request.POST.get("charter_text", "")
        settings_obj.save()
        messages.success(request, "Settings updated.")
        return redirect("site-settings")

    return render(request, "site_settings.html", {"settings_obj": settings_obj})


@staff_member_required
def merits_page(request):
    """Merit catalog management page. Superuser only."""
    return render(request, "merits_manage.html")


@login_required
@require_GET
def api_status(request):
    """Return game state overview: version, game date, entity counts."""
    from agencies.models import Agency, CouncilItem, GlobalFlaw, FTLProject
    from characters.models import Character
    from comms.models import Thread
    from django.contrib.auth.models import User
    from npcs.models import NPC

    settings_obj = SiteSettings.load()
    version_file = Path(__file__).resolve().parent.parent / "version.txt"
    version = version_file.read_text().strip() if version_file.exists() else "unknown"

    return JsonResponse({
        "appVersion": version,
        "nextGameDate": str(settings_obj.next_game_date) if settings_obj.next_game_date else None,
        "charterTextLength": len(settings_obj.charter_text or ""),
        "counts": {
            "users": User.objects.count(),
            "characters": Character.objects.count(),
            "playerAgencies": Agency.objects.filter(is_player_agency=True).count(),
            "npcAgencies": Agency.objects.filter(is_player_agency=False).count(),
            "npcs": NPC.objects.count(),
            "activeNpcs": NPC.objects.filter(state="active").count(),
            "councilItems": CouncilItem.objects.count(),
            "votingItems": CouncilItem.objects.filter(status="voting").count(),
            "globalFlaws": GlobalFlaw.objects.count(),
            "ftlProjects": FTLProject.objects.count(),
            "threads": Thread.objects.count(),
            "pullingStrings": PullingString.objects.count(),
        },
    })


# ---------------------------------------------------------------------------
# Pulling Strings catalog API
# ---------------------------------------------------------------------------

def _serialize_ps(ps):
    """Serialize a PullingString catalog entry."""
    return {
        "id": ps.id,
        "name": ps.name,
        "description": ps.description,
        "cost": ps.cost,
        "category": ps.category,
        "isLinkable": ps.is_linkable,
    }


@login_required
@require_http_methods(["GET", "POST"])
def api_pulling_strings(request):
    """GET: list all pulling strings. POST: create (admin only)."""
    if request.method == "GET":
        qs = PullingString.objects.all()
        # Non-superusers cannot see AI-category pulling strings
        if not request.user.is_superuser:
            qs = qs.exclude(category="ai")
        return JsonResponse([_serialize_ps(ps) for ps in qs], safe=False)

    if not request.user.is_superuser:
        return JsonResponse(
            {"error": "ACCESS DENIED. Administrator clearance required."},
            status=403,
        )

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid data stream."}, status=400)

    valid_categories = [c[0] for c in PullingString.CATEGORY_CHOICES]
    category = data.get("category", "general")
    if category not in valid_categories:
        return JsonResponse({"error": f"Invalid category. Use: {valid_categories}"}, status=400)

    ps = PullingString.objects.create(
        name=data.get("name", ""),
        description=data.get("description", ""),
        cost=data.get("cost", 0),
        category=category,
        is_linkable=bool(data.get("isLinkable", False)),
    )
    return JsonResponse(_serialize_ps(ps), status=201)


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
def api_pulling_string_detail(request, pk):
    """GET: single pulling string. PUT/DELETE: admin only."""
    from django.shortcuts import get_object_or_404
    ps = get_object_or_404(PullingString, pk=pk)

    if request.method == "GET":
        if ps.category == "ai" and not request.user.is_superuser:
            return JsonResponse({"error": "ACCESS DENIED."}, status=403)
        return JsonResponse(_serialize_ps(ps))

    if not request.user.is_superuser:
        return JsonResponse(
            {"error": "ACCESS DENIED. Administrator clearance required."},
            status=403,
        )

    if request.method == "PUT":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid data stream."}, status=400)

        for field in ("name", "description"):
            if field in data:
                setattr(ps, field, data[field])
        if "cost" in data:
            ps.cost = data["cost"]
        if "category" in data:
            valid_categories = [c[0] for c in PullingString.CATEGORY_CHOICES]
            if data["category"] in valid_categories:
                ps.category = data["category"]
        if "isLinkable" in data:
            ps.is_linkable = bool(data["isLinkable"])
        ps.save()
        return JsonResponse(_serialize_ps(ps))

    if request.method == "DELETE":
        ps.delete()
        return JsonResponse({"status": "Record terminated."})


# ---------------------------------------------------------------------------
# Merits catalog API
# ---------------------------------------------------------------------------

def _serialize_merit(m):
    """Serialize a MeritDefinition catalog entry."""
    return {
        "id": m.id,
        "name": m.name,
        "description": m.description,
        "cost": m.cost,
        "minCost": m.min_cost,
        "category": m.category,
        "classRestriction": m.class_restriction,
        "prerequisites": m.prerequisites,
        "effects": m.effects,
    }


@login_required
@require_http_methods(["GET", "POST"])
def api_merits(request):
    """GET: list all merit definitions. POST: create (admin only)."""
    if request.method == "GET":
        return JsonResponse(
            [_serialize_merit(m) for m in MeritDefinition.objects.all()],
            safe=False,
        )

    if not request.user.is_superuser:
        return JsonResponse(
            {"error": "ACCESS DENIED. Administrator clearance required."},
            status=403,
        )

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid data stream."}, status=400)

    valid_categories = [c[0] for c in MeritDefinition.CATEGORY_CHOICES]
    category = data.get("category", "physical")
    if category not in valid_categories:
        return JsonResponse(
            {"error": f"Invalid category. Use: {valid_categories}"}, status=400
        )

    cost = data.get("cost", 1)
    min_cost = data.get("minCost", cost)

    m = MeritDefinition.objects.create(
        name=data.get("name", ""),
        description=data.get("description", ""),
        cost=cost,
        min_cost=min_cost,
        category=category,
        class_restriction=data.get("classRestriction", ""),
        prerequisites=data.get("prerequisites", ""),
        effects=data.get("effects", {}),
    )
    return JsonResponse(_serialize_merit(m), status=201)


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
def api_merit_detail(request, pk):
    """GET: single merit. PUT/DELETE: admin only."""
    from django.shortcuts import get_object_or_404

    m = get_object_or_404(MeritDefinition, pk=pk)

    if request.method == "GET":
        return JsonResponse(_serialize_merit(m))

    if not request.user.is_superuser:
        return JsonResponse(
            {"error": "ACCESS DENIED. Administrator clearance required."},
            status=403,
        )

    if request.method == "PUT":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid data stream."}, status=400)

        for field in ("name", "description", "prerequisites"):
            if field in data:
                setattr(m, field, data[field])
        if "cost" in data:
            m.cost = data["cost"]
        if "minCost" in data:
            m.min_cost = data["minCost"]
        if "category" in data:
            valid_categories = [c[0] for c in MeritDefinition.CATEGORY_CHOICES]
            if data["category"] in valid_categories:
                m.category = data["category"]
        if "classRestriction" in data:
            m.class_restriction = data["classRestriction"]
        if "effects" in data:
            m.effects = data["effects"]
        m.save()
        return JsonResponse(_serialize_merit(m))

    if request.method == "DELETE":
        m.delete()
        return JsonResponse({"status": "Record terminated."})
