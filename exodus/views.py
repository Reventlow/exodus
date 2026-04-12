"""Core views for Exodus site settings."""

import json
from pathlib import Path

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .models import MeritDefinition, PullingString, SiteSettings

User = get_user_model()


@login_required
@require_GET
def starmap_demo(request):
    """3D star map demo — superuser only."""
    if not request.user.is_superuser:
        return HttpResponseForbidden("ACCESS DENIED. Superuser clearance required.")
    return render(request, "starmap/demo.html")


@staff_member_required
def site_settings(request):
    """Allow staff to update site-wide settings."""
    settings_obj = SiteSettings.load()

    if request.method == "POST":
        date_value = request.POST.get("next_game_date", "").strip()
        settings_obj.next_game_date = date_value or None
        settings_obj.charter_text = request.POST.get("charter_text", "")
        settings_obj.lock_comms = "lock_comms" not in request.POST
        settings_obj.show_world_map = "show_world_map" in request.POST
        settings_obj.show_star_map = "show_star_map" in request.POST
        settings_obj.show_starships = "show_starships" in request.POST
        settings_obj.show_council = "show_council" in request.POST
        settings_obj.council_mode = request.POST.get("council_mode", "agency")
        settings_obj.enforce_ship_slot_budget = "enforce_ship_slot_budget" in request.POST
        for lbl in ["dispatch", "players", "agencies", "council", "npcs", "comms"]:
            val = request.POST.get(f"label_{lbl}", "").strip()
            if val:
                setattr(settings_obj, f"label_{lbl}", val)
        settings_obj.save()
        messages.success(request, "Settings updated.")
        return redirect("site-settings")

    from agencies.models import Agency
    users = User.objects.filter(is_active=True).order_by("username")
    impersonating = request.session.get("_impersonate_real_user_id")
    all_agencies = Agency.objects.order_by("name")
    player_agencies = all_agencies.filter(is_player_agency=True)
    npc_agencies = all_agencies.filter(is_player_agency=False)
    return render(request, "site_settings.html", {
        "settings_obj": settings_obj,
        "users": users,
        "impersonating": impersonating,
        "player_agencies": player_agencies,
        "npc_agencies": npc_agencies,
    })


@login_required
@require_POST
def impersonate_user(request):
    """Log in as another user (superuser only). Stores real user ID in session."""
    if not request.user.is_superuser and "_impersonate_real_user_id" not in request.session:
        return HttpResponseForbidden("ACCESS DENIED.")

    target_id = request.POST.get("user_id")
    if not target_id:
        return redirect("site-settings")

    target = User.objects.filter(pk=target_id).first()
    if not target:
        messages.error(request, "User not found.")
        return redirect("site-settings")

    # Store real superuser ID before switching
    real_user_id = request.session.get("_impersonate_real_user_id") or request.user.pk

    login(request, target, backend="django.contrib.auth.backends.ModelBackend")
    # Restore after login() flushes the session
    request.session["_impersonate_real_user_id"] = real_user_id
    messages.success(request, f"Now viewing as {target.username}.")
    return redirect("/")


@login_required
def stop_impersonation(request):
    """Return to the real superuser account."""
    real_user_id = request.session.get("_impersonate_real_user_id")
    if real_user_id:
        real_user = User.objects.filter(pk=real_user_id).first()
        if real_user:
            del request.session["_impersonate_real_user_id"]
            login(request, real_user, backend="django.contrib.auth.backends.ModelBackend")
            messages.success(request, f"Returned to {real_user.username}.")
            return redirect("site-settings")

    # Fallback: if no impersonation session, try to find the superuser
    superuser = User.objects.filter(is_superuser=True).first()
    if superuser:
        request.session.pop("_impersonate_real_user_id", None)
        login(request, superuser, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, f"Returned to {superuser.username}.")
        return redirect("site-settings")

    return redirect("/")


@login_required
@require_POST
def api_transfer_player_to_agency(request):
    """Transfer a player's character and NPCs to another agency as NPC dossiers."""
    if not request.user.is_superuser:
        return JsonResponse({"error": "ACCESS DENIED."}, status=403)

    from django.db import transaction
    from django.core.files.base import ContentFile
    from characters.models import Character
    from npcs.models import NPC, NpcMerit, NpcPullingString
    from agencies.models import Agency, Base

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    source_user_id = body.get("sourceUserId")
    target_agency_id = body.get("targetAgencyId")
    source_agency_id = body.get("sourceAgencyId")
    transfer_xp = body.get("transferXp", False)

    source_user = User.objects.filter(pk=source_user_id).first()
    if not source_user:
        return JsonResponse({"error": "Source user not found."}, status=400)

    character = Character.objects.filter(owner=source_user).first()
    if not character:
        return JsonResponse({"error": "Source user has no character."}, status=400)

    target_agency = Agency.objects.filter(pk=target_agency_id).first()
    if not target_agency:
        return JsonResponse({"error": "Target agency not found."}, status=400)

    source_agency = None
    if source_agency_id:
        source_agency = Agency.objects.filter(pk=source_agency_id).first()

    with transaction.atomic():
        # Create NPC dossier from character
        npc = NPC.objects.create(
            name=character.name,
            character_class=character.character_class,
            bio=character.dossier or "",
            attributes=character.attributes,
            skills=character.skills,
            health_bashing=getattr(character, "health_bashing", 0),
            health_lethal=getattr(character, "health_lethal", 0),
            health_aggravated=getattr(character, "health_aggravated", 0),
            size=character.size,
            mental_load=character.mental_load or 0,
            willpower_current=character.willpower_current or 0,
            experience=character.experience or 0,
            experience_used=character.experience_used or 0,
            flaws=character.flaws or [],
            specialisations=character.specialisations if hasattr(character, "specialisations") else [],
            is_npc_dossier=True,
            agency=target_agency,
            created_by=request.user,
            state="active",
        )

        # Copy profile picture
        if character.profile_picture:
            try:
                name = character.profile_picture.name.split("/")[-1]
                npc.image.save(name, ContentFile(character.profile_picture.read()), save=True)
            except Exception:
                pass

        # Copy merits
        for cm in character.character_merits.select_related("merit").all():
            NpcMerit.objects.create(npc=npc, merit=cm.merit, rating=cm.rating)

        # Copy pulling strings
        for cps in character.character_pulling_strings.select_related("pulling_string").all():
            NpcPullingString.objects.create(npc=npc, pulling_string=cps.pulling_string)

        # Transfer existing player NPCs to target agency
        npcs_moved = NPC.objects.filter(assigned_to=source_user).update(
            is_npc_dossier=True, agency=target_agency, assigned_to=None
        )

        # Clean up workspace assignments referencing this character
        char_id = character.id
        for base in Base.objects.all():
            if base.workspaces:
                cleaned = [
                    ws for ws in base.workspaces
                    if not (ws.get("assignedType") == "character" and ws.get("assignedTo") == char_id)
                ]
                if len(cleaned) != len(base.workspaces):
                    base.workspaces = cleaned
                    base.save(update_fields=["workspaces"])

        # Transfer XP and merits from source agency
        xp_transferred = 0
        merits_transferred = 0
        if transfer_xp and source_agency:
            xp_transferred = source_agency.experience
            target_agency.experience = (target_agency.experience or 0) + xp_transferred
            source_agency.experience = 0
            # Transfer merits
            src_merits = source_agency.merits or []
            tgt_merits = target_agency.merits or []
            merits_transferred = len(src_merits)
            target_agency.merits = tgt_merits + src_merits
            source_agency.merits = []
            source_agency.save(update_fields=["experience", "merits"])
            target_agency.save(update_fields=["experience", "merits"])

        # Delete the character
        char_name = character.name
        character.delete()

    return JsonResponse({
        "status": "Transfer complete.",
        "character": char_name,
        "npcDossierId": npc.id,
        "npcsMoved": npcs_moved,
        "xpTransferred": xp_transferred,
        "meritsTransferred": merits_transferred,
        "targetAgency": target_agency.name,
    })


@login_required
def pulling_strings_page(request):
    """Pulling strings catalog page. Staff can edit, players can view."""
    # Get player's character class for filtering
    char_class = ""
    if not request.user.is_superuser:
        from characters.models import Character
        char = Character.objects.filter(owner=request.user).first()
        if char:
            char_class = char.character_class
    return render(request, "pulling_strings_manage.html", {
        "is_admin": request.user.is_superuser,
        "character_class": char_class,
    })


@login_required
def merits_page(request):
    """Merit catalog page. Staff can edit, players can view."""
    char_class = ""
    if not request.user.is_superuser:
        from characters.models import Character
        char = Character.objects.filter(owner=request.user).first()
        if char:
            char_class = char.character_class
    return render(request, "merits_manage.html", {
        "is_admin": request.user.is_superuser,
        "character_class": char_class,
    })


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
