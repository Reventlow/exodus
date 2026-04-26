import json
from pathlib import Path

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.db import transaction
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from .models import Agency, ChangeRequest, GlobalFlaw, FTLProject, AgencyFTLProject, CouncilItem, CouncilVote, BaseConfig, Base, AgencyStatLog, ProjectRollLog
from .serializers import (
    serialize_agency,
    serialize_agency_summary,
    serialize_agency_section,
    serialize_base_section,
    serialize_change_request,
    serialize_global_flaw,
    serialize_ftl_project,
    serialize_agency_ftl_project,
    serialize_council_item,
    serialize_base,
    serialize_base_config,
    build_vote_record,
)

COUNCIL_GROUP = "council_votes"


def _is_fixer(user):
    """Check if the user's character has the fixer class."""
    from characters.models import Character
    char = Character.objects.filter(owner=user).first()
    return char and char.character_class == "fixer"


def _require_fixer(user):
    """Return a 403 JsonResponse if the user is not a fixer, or None if OK."""
    if user.is_superuser:
        return None
    if not _is_fixer(user):
        return JsonResponse(
            {"error": "ACCESS DENIED. Council actions require Fixer clearance."},
            status=403,
        )
    return None


def _broadcast_council_item(ci):
    """Broadcast an updated council item to all WebSocket clients."""
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        COUNCIL_GROUP,
        {
            "type": "council_update",
            "item": serialize_council_item(ci, request.user),
        },
    )


# ---------------------------------------------------------------------------
# Page views (return HTML)
# ---------------------------------------------------------------------------


@login_required
def agency_list_page(request):
    """Dashboard showing all agencies."""
    return render(request, "agencies/list.html")


@login_required
def world_map_page(request):
    """Interactive world map showing agency territories and base locations."""
    return render(request, "agencies/world_map.html", {
        "is_admin": request.user.is_superuser,
    })


@login_required
@require_http_methods(["GET"])
def api_map_data(request):
    """Return map data: agency territories (countries) and base markers."""
    is_admin = request.user.is_superuser
    agencies = Agency.objects.all()
    if not is_admin:
        agencies = agencies.filter(is_hidden=False)

    data = []
    for agency in agencies:
        countries = (agency.alliance or {}).get("countries", [])
        bases_qs = agency.bases.all() if is_admin else agency.bases.filter(is_hidden=False)
        bases = []
        for b in bases_qs:
            if b.latitude is None or b.longitude is None:
                continue
            # Hide coordinates classified via hidden_sections for non-admins
            if not is_admin and "coordinates" in (b.hidden_sections or []):
                continue
            bases.append({
                "id": b.id,
                "name": b.name,
                "lat": b.latitude,
                "lng": b.longitude,
            })
        data.append({
            "id": agency.id,
            "name": agency.name,
            "color": agency.map_color or ("#00ff88" if agency.is_player_agency else "#e05555"),
            "isPlayerAgency": agency.is_player_agency,
            "countries": countries,
            "bases": bases,
        })
    return JsonResponse(data, safe=False)


@login_required
def agency_sheet_page(request, pk):
    """Agency sheet page. Shows full agency with React frontend."""
    agency = get_object_or_404(Agency, pk=pk)
    if agency.is_hidden and not request.user.is_superuser:
        return HttpResponseForbidden("ACCESS DENIED. Agency record not found.")
    is_admin = request.user.is_superuser
    from characters.models import Character
    char = Character.objects.filter(owner=request.user).first()
    char_class = char.character_class if char else ""
    return render(
        request,
        "agencies/sheet.html",
        {
            "agency_id": agency.id,
            "is_admin": is_admin,
            "is_player_agency": agency.is_player_agency,
            "character_class": char_class,
        },
    )


@login_required
def global_flaws_page(request):
    """Global flaws management page. Superuser only."""
    if not request.user.is_superuser:
        return JsonResponse(
            {"error": "ACCESS DENIED. Administrator clearance required."}, status=403
        )
    return render(request, "agencies/global_flaws.html")


@login_required
def ftl_projects_page(request):
    """FTL projects management page. Superuser only."""
    if not request.user.is_superuser:
        return JsonResponse(
            {"error": "ACCESS DENIED. Administrator clearance required."}, status=403
        )
    return render(request, "agencies/ftl_projects.html")


@login_required
def council_page(request):
    """United Interstellar Council page. Viewable by all, editable by superusers."""
    user_agency = None
    is_chairman = False
    if not request.user.is_superuser:
        char_ids = set(
            request.user.characters.values_list("id", flat=True)
        )
        if char_ids:
            for base in Base.objects.filter(
                agency__is_player_agency=True
            ).select_related("agency"):
                for ws in base.workspaces or []:
                    if (
                        ws.get("assignedType") == "character"
                        and ws.get("assignedTo") in char_ids
                    ):
                        user_agency = base.agency
                        is_chairman = base.agency.is_council_chairman
                        break
                if user_agency:
                    break
    agencies_qs = Agency.objects.order_by("name")
    if not request.user.is_superuser:
        agencies_qs = agencies_qs.filter(is_hidden=False)
    agencies = list(agencies_qs.values_list("id", "name"))
    return render(
        request,
        "agencies/council.html",
        {
            "user_agency_id": user_agency.id if user_agency else 0,
            "user_agency_name": user_agency.name if user_agency else "",
            "is_chairman": is_chairman,
            "is_fixer": _is_fixer(request.user),
            "agencies_json": json.dumps(
                [{"id": a[0], "name": a[1]} for a in agencies]
            ),
        },
    )


@login_required
def council_charter_page(request):
    """UIC Charter page. Readable by all logged-in users."""
    from exodus.models import SiteSettings

    site = SiteSettings.load()
    charter_content = site.charter_text
    # Fallback to file if DB is empty (first-time migration)
    if not charter_content:
        charter_path = Path(settings.BASE_DIR) / "UIC_CHARTER.md"
        if charter_path.exists():
            charter_content = charter_path.read_text()
    return render(request, "agencies/council_charter.html", {"charter_md": charter_content})


# ---------------------------------------------------------------------------
# API views (return JSON)
# ---------------------------------------------------------------------------


@login_required
@require_http_methods(["GET", "POST"])
def api_agency_list(request):
    """GET: list all agencies. POST: create a new agency (admin only)."""
    if request.method == "GET":
        agencies = Agency.objects.all()
        if not request.user.is_superuser:
            agencies = agencies.filter(is_hidden=False)
        data = [serialize_agency_summary(a, request.user) for a in agencies]
        return JsonResponse(data, safe=False)

    # POST — admin only
    if not request.user.is_superuser:
        return JsonResponse(
            {"error": "ACCESS DENIED. Administrator clearance required."}, status=403
        )

    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        body = {}

    agency = Agency.objects.create(
        name=body.get("name", "NEW AGENCY"),
        is_player_agency=body.get("isPlayerAgency", False),
    )
    return JsonResponse(serialize_agency(agency, request.user), status=201)


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
def api_agency_detail(request, pk):
    """GET: full agency data. PUT: update (admin only). DELETE: admin only."""
    agency = get_object_or_404(Agency, pk=pk)

    if agency.is_hidden and not request.user.is_superuser:
        return JsonResponse(
            {"error": "ACCESS DENIED. Agency record not found."}, status=404
        )

    if request.method == "GET":
        return JsonResponse(serialize_agency(agency, request.user))

    # PUT / DELETE — admin only
    if not request.user.is_superuser:
        return JsonResponse(
            {"error": "ACCESS DENIED. Administrator clearance required."}, status=403
        )

    if request.method == "PUT":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid data stream."}, status=400)

        # Update text fields
        for field in ("name", "alliance", "motto", "headquarters", "notes"):
            if field in data:
                setattr(agency, field, data[field])

        # Update numeric fields
        if "integrity" in data:
            agency.integrity = data["integrity"]
        if "experience" in data:
            agency.experience = data["experience"]
        if "zeroDayPool" in data:
            agency.zero_day_pool = data["zeroDayPool"]
        if "sweepPool" in data:
            agency.sweep_pool = data["sweepPool"]
        if "isNuclearPower" in data:
            agency.is_nuclear_power = bool(data["isNuclearPower"])

        # Update booleans
        if "isPlayerAgency" in data:
            agency.is_player_agency = data["isPlayerAgency"]
        if "isCouncilMember" in data:
            agency.is_council_member = data["isCouncilMember"]
            # If leaving the council, also remove chairman status
            if not data["isCouncilMember"]:
                agency.is_council_chairman = False

        # Update JSON fields
        if "attributes" in data:
            agency.attributes = data["attributes"]
        if "specializations" in data:
            agency.specializations = data["specializations"]
        if "merits" in data:
            agency.merits = data["merits"]
        if "flaws" in data:
            agency.flaws = data["flaws"]
        if "assets" in data:
            agency.assets = data["assets"]
        if "fleet" in data:
            agency.fleet = data["fleet"]
        if "conditions" in data:
            agency.conditions = data["conditions"]
        if "projects" in data:
            # Log completion changes by superuser
            old_projects = agency.projects or []
            new_projects = data["projects"]
            for idx, new_p in enumerate(new_projects):
                if not isinstance(new_p, dict):
                    continue
                old_p = old_projects[idx] if idx < len(old_projects) and isinstance(old_projects[idx], dict) else {}
                old_score = int(old_p.get("completionScore", 0))
                new_score = int(new_p.get("completionScore", 0))
                if old_score != new_score:
                    try:
                        ProjectRollLog.objects.create(
                            agency=agency,
                            project_index=idx,
                            project_name=new_p.get("name", ""),
                            character_name="GM",
                            roll_type="manual",
                            pool=0,
                            rolls=[],
                            successes=new_score - old_score,
                            auto_successes=0,
                            mental_damage=False,
                            old_score=old_score,
                            new_score=new_score,
                            message=f"GM adjusted completion: {old_score} → {new_score}.",
                        )
                    except Exception:
                        pass
            # Strip computed fields before persisting
            agency.projects = [
                {k: v for k, v in p.items() if k != "computedPool"} if isinstance(p, dict) else p
                for p in new_projects
            ]
        if "history" in data:
            agency.history = data["history"]
        if "projectRolls" in data:
            agency.project_rolls = data["projectRolls"]
        if "isHidden" in data:
            agency.is_hidden = bool(data["isHidden"])
        if "mapColor" in data:
            agency.map_color = data["mapColor"]

        agency.save()
        return JsonResponse(serialize_agency(agency, request.user))

    if request.method == "DELETE":
        agency.delete()
        return JsonResponse({"status": "Agency record terminated."})


@login_required
@require_http_methods(["POST"])
def api_toggle_visibility(request, pk):
    """Toggle visibility of a specific field on an NPC agency. Admin only."""
    if not request.user.is_superuser:
        return JsonResponse({"error": "ACCESS DENIED."}, status=403)

    agency = get_object_or_404(Agency, pk=pk)
    if agency.is_player_agency:
        return JsonResponse(
            {"error": "Visibility controls are only for NPC agencies."}, status=400
        )

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid data stream."}, status=400)

    field = data.get("field")
    visible = data.get("visible")

    if not field or visible is None:
        return JsonResponse(
            {"error": "Both 'field' and 'visible' are required."}, status=400
        )

    visibility = agency.field_visibility or {}
    visibility[field] = bool(visible)
    agency.field_visibility = visibility
    agency.save(update_fields=["field_visibility", "updated_at"])

    return JsonResponse({"field": field, "visible": visibility[field]})


@login_required
@require_http_methods(["GET", "POST"])
def api_change_request_list(request, pk):
    """GET: list change requests for an agency. POST: submit a new one."""
    agency = get_object_or_404(Agency, pk=pk)

    if not agency.is_player_agency:
        return JsonResponse(
            {"error": "Change requests are only for the player agency."}, status=400
        )

    if request.method == "GET":
        qs = agency.change_requests.select_related("requester", "reviewed_by")
        # Admin sees all; players see only their own
        if not request.user.is_superuser:
            qs = qs.filter(requester=request.user)
        data = [serialize_change_request(cr) for cr in qs]
        return JsonResponse(data, safe=False)

    # POST — any authenticated user can submit
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid data stream."}, status=400)

    field_name = data.get("fieldName", "")
    description = data.get("description", "")
    proposed_changes = data.get("proposedChanges", {})

    if not field_name or not description:
        return JsonResponse(
            {"error": "fieldName and description are required."}, status=400
        )

    cr = ChangeRequest.objects.create(
        agency=agency,
        requester=request.user,
        field_name=field_name,
        description=description,
        proposed_changes=proposed_changes,
    )
    return JsonResponse(serialize_change_request(cr), status=201)


@login_required
@require_http_methods(["PUT"])
def api_change_request_review(request, pk):
    """Admin approves or rejects a change request."""
    if not request.user.is_superuser:
        return JsonResponse({"error": "ACCESS DENIED."}, status=403)

    cr = get_object_or_404(
        ChangeRequest.objects.select_related("agency"), pk=pk
    )

    if cr.status != "pending":
        return JsonResponse(
            {"error": "This request has already been reviewed."}, status=400
        )

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid data stream."}, status=400)

    action = data.get("action")  # "approve" or "reject"
    admin_note = data.get("adminNote", "")

    if action not in ("approve", "reject"):
        return JsonResponse(
            {"error": "action must be 'approve' or 'reject'."}, status=400
        )

    cr.admin_note = admin_note
    cr.reviewed_by = request.user
    cr.reviewed_at = timezone.now()

    if action == "approve":
        cr.status = "approved"
        # Apply proposed changes to the agency
        _apply_changes(cr.agency, cr.proposed_changes)
        cr.agency.save()
    else:
        cr.status = "rejected"

    cr.save()
    return JsonResponse(serialize_change_request(cr))


@login_required
@require_http_methods(["GET"])
def api_notification_count(request):
    """Return notification counts for the current user."""
    counts = {"pendingRequests": 0, "reviewedRequests": 0}

    if request.user.is_superuser:
        # Admin sees count of pending change requests
        counts["pendingRequests"] = ChangeRequest.objects.filter(
            status="pending"
        ).count()
    else:
        # Player sees count of recently reviewed (non-pending) requests they made
        counts["reviewedRequests"] = ChangeRequest.objects.filter(
            requester=request.user, status__in=["approved", "rejected"]
        ).count()

    return JsonResponse(counts)


@login_required
@require_http_methods(["GET", "POST"])
def api_global_flaw_list(request):
    """GET: list all global flaws. POST: create a new one (admin only)."""
    if not request.user.is_superuser:
        return JsonResponse(
            {"error": "ACCESS DENIED. Administrator clearance required."}, status=403
        )

    if request.method == "GET":
        flaws = GlobalFlaw.objects.all()
        data = [serialize_global_flaw(gf) for gf in flaws]
        return JsonResponse(data, safe=False)

    # POST
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        body = {}

    gf = GlobalFlaw.objects.create(
        name=body.get("name", "NEW GLOBAL FLAW"),
        value=body.get("value", 0),
        description=body.get("description", ""),
        order=body.get("order", 0),
    )
    return JsonResponse(serialize_global_flaw(gf), status=201)


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
def api_global_flaw_detail(request, pk):
    """GET/PUT/DELETE a single global flaw. Admin only."""
    if not request.user.is_superuser:
        return JsonResponse(
            {"error": "ACCESS DENIED. Administrator clearance required."}, status=403
        )

    gf = get_object_or_404(GlobalFlaw, pk=pk)

    if request.method == "GET":
        return JsonResponse(serialize_global_flaw(gf))

    if request.method == "PUT":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid data stream."}, status=400)

        if "name" in data:
            gf.name = data["name"]
        if "value" in data:
            gf.value = data["value"]
        if "description" in data:
            gf.description = data["description"]
        if "order" in data:
            gf.order = data["order"]

        gf.save()
        return JsonResponse(serialize_global_flaw(gf))

    if request.method == "DELETE":
        gf.delete()
        return JsonResponse({"status": "Global flaw record terminated."})


# ---------------------------------------------------------------------------
# API views — FTL Projects (global CRUD, superuser only)
# ---------------------------------------------------------------------------


@login_required
@require_http_methods(["GET", "POST"])
def api_ftl_project_list(request):
    """GET: list all FTL projects. POST: create a new one (admin only)."""
    if not request.user.is_superuser:
        return JsonResponse(
            {"error": "ACCESS DENIED. Administrator clearance required."}, status=403
        )

    if request.method == "GET":
        projects = FTLProject.objects.all()
        data = [serialize_ftl_project(fp) for fp in projects]
        return JsonResponse(data, safe=False)

    # POST
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        body = {}

    fp = FTLProject.objects.create(
        name=body.get("name", "NEW FTL PROJECT"),
        description=body.get("description", ""),
        pros=body.get("pros", []),
        cons=body.get("cons", []),
        required_successes=body.get("requiredSuccesses", 10),
    )
    return JsonResponse(serialize_ftl_project(fp), status=201)


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
def api_ftl_project_detail(request, pk):
    """GET/PUT/DELETE a single FTL project. Admin only."""
    if not request.user.is_superuser:
        return JsonResponse(
            {"error": "ACCESS DENIED. Administrator clearance required."}, status=403
        )

    fp = get_object_or_404(FTLProject, pk=pk)

    if request.method == "GET":
        return JsonResponse(serialize_ftl_project(fp))

    if request.method == "PUT":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid data stream."}, status=400)

        if "name" in data:
            fp.name = data["name"]
        if "description" in data:
            fp.description = data["description"]
        if "pros" in data:
            fp.pros = data["pros"]
        if "cons" in data:
            fp.cons = data["cons"]
        if "requiredSuccesses" in data:
            fp.required_successes = data["requiredSuccesses"]

        fp.save()
        return JsonResponse(serialize_ftl_project(fp))

    if request.method == "DELETE":
        fp.delete()
        return JsonResponse({"status": "FTL project record terminated."})


# ---------------------------------------------------------------------------
# API views — Agency FTL Assignments (superuser only)
# ---------------------------------------------------------------------------


@login_required
@require_http_methods(["POST"])
def api_agency_ftl_assign(request, pk):
    """Assign an FTL project to an agency. Body: {ftlProjectId: int}."""
    if not request.user.is_superuser:
        return JsonResponse(
            {"error": "ACCESS DENIED. Administrator clearance required."}, status=403
        )

    agency = get_object_or_404(Agency, pk=pk)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid data stream."}, status=400)

    ftl_project_id = data.get("ftlProjectId")
    if not ftl_project_id:
        return JsonResponse({"error": "ftlProjectId is required."}, status=400)

    ftl_project = get_object_or_404(FTLProject, pk=ftl_project_id)

    # Check if already assigned
    if AgencyFTLProject.objects.filter(agency=agency, ftl_project=ftl_project).exists():
        return JsonResponse(
            {"error": "FTL project already assigned to this agency."}, status=400
        )

    afp = AgencyFTLProject.objects.create(agency=agency, ftl_project=ftl_project)
    return JsonResponse(serialize_agency_ftl_project(afp), status=201)


@login_required
@require_http_methods(["PUT", "DELETE"])
def api_agency_ftl_detail(request, pk, assignment_id):
    """PUT: update current_successes. DELETE: unassign FTL project. Admin only."""
    if not request.user.is_superuser:
        return JsonResponse(
            {"error": "ACCESS DENIED. Administrator clearance required."}, status=403
        )

    afp = get_object_or_404(AgencyFTLProject, pk=assignment_id, agency_id=pk)

    if request.method == "DELETE":
        afp.delete()
        return JsonResponse({"status": "FTL assignment terminated."})

    # PUT — update current_successes
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid data stream."}, status=400)

    if "currentSuccesses" in data:
        old_score = afp.current_successes
        afp.current_successes = data["currentSuccesses"]
        afp.save(update_fields=["current_successes"])
        if old_score != afp.current_successes:
            try:
                ProjectRollLog.objects.create(
                    agency=afp.agency,
                    assignment=afp,
                    character_name="GM",
                    roll_type="manual",
                    pool=0,
                    rolls=[],
                    successes=afp.current_successes - old_score,
                    auto_successes=0,
                    mental_damage=False,
                    old_score=old_score,
                    new_score=afp.current_successes,
                    message=f"GM adjusted progress: {old_score} → {afp.current_successes}.",
                )
            except Exception:
                pass

    return JsonResponse(serialize_agency_ftl_project(afp))


# ---------------------------------------------------------------------------
# API views — Council Items
# ---------------------------------------------------------------------------


@login_required
@require_http_methods(["GET", "POST"])
def api_council_list(request):
    """GET: list all council items. POST: create a new one (admin only)."""
    if request.method == "GET":
        items = CouncilItem.objects.all()
        data = [serialize_council_item(ci, request.user) for ci in items]
        return JsonResponse(data, safe=False)

    # POST — fixer class required
    denied = _require_fixer(request.user)
    if denied:
        return denied
    if not request.user.is_superuser:
        # Check the user has an agency (via character workspace assignment)
        char_ids = set(
            request.user.characters.values_list("id", flat=True)
        )
        user_agency = None
        if char_ids:
            for base in Base.objects.filter(
                agency__is_player_agency=True
            ).select_related("agency"):
                for ws in base.workspaces or []:
                    if (
                        ws.get("assignedType") == "character"
                        and ws.get("assignedTo") in char_ids
                    ):
                        user_agency = base.agency
                        break
                if user_agency:
                    break
        if not user_agency:
            return JsonResponse(
                {"error": "ACCESS DENIED. No agency affiliation found."},
                status=403,
            )

    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        body = {}

    # Admin can set proposedBy freely; players auto-set to their agency
    if request.user.is_superuser:
        proposed_by = body.get("proposedBy", "")
    else:
        proposed_by = user_agency.name

    ci = CouncilItem.objects.create(
        name=body.get("name", "NEW COUNCIL ITEM"),
        item_type=body.get("itemType", "agreement"),
        description=body.get("description", ""),
        status=body.get("status", "proposed"),
        proposed_by=proposed_by,
        notes=body.get("notes", ""),
        order=body.get("order", 0),
    )
    return JsonResponse(serialize_council_item(ci, request.user), status=201)


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
def api_council_detail(request, pk):
    """GET/PUT/DELETE a single council item."""
    ci = get_object_or_404(CouncilItem, pk=pk)

    if request.method == "GET":
        return JsonResponse(serialize_council_item(ci, request.user))

    # PUT/DELETE — fixer class required
    denied = _require_fixer(request.user)
    if denied:
        return denied

    # Non-admin: players can edit/delete own proposals, chairman can change status
    if not request.user.is_superuser:
        if request.method not in ("PUT", "DELETE"):
            return JsonResponse(
                {"error": "ACCESS DENIED. Administrator clearance required."},
                status=403,
            )
        # Find the user's agency
        char_ids = set(
            request.user.characters.values_list("id", flat=True)
        )
        user_agency = None
        if char_ids:
            for base in Base.objects.filter(
                agency__is_player_agency=True
            ).select_related("agency"):
                for ws in base.workspaces or []:
                    if (
                        ws.get("assignedType") == "character"
                        and ws.get("assignedTo") in char_ids
                    ):
                        user_agency = base.agency
                        break
                if user_agency:
                    break
        user_agency_name = user_agency.name if user_agency else None
        is_chairman = user_agency.is_council_chairman if user_agency else False

        # Parse body for PUT
        if request.method == "PUT":
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse({"error": "Invalid data stream."}, status=400)

            # Chairman status transitions
            new_status = data.get("status")
            if new_status and is_chairman:
                # proposed → voting
                if ci.status == "proposed" and new_status == "voting":
                    ci.status = "voting"
                    ci.save()
                    _broadcast_council_item(ci)
                    return JsonResponse(serialize_council_item(ci, request.user))
                # voting → emergency_suspended
                if ci.status == "voting" and new_status == "emergency_suspended":
                    ci.vote_record = build_vote_record(ci)
                    ci.status = "emergency_suspended"
                    ci.save()
                    _broadcast_council_item(ci)
                    return JsonResponse(serialize_council_item(ci, request.user))

            # Own proposal editing (proposed status only)
            if (
                user_agency_name
                and ci.proposed_by == user_agency_name
                and ci.status == "proposed"
            ):
                for field, attr in [
                    ("name", "name"),
                    ("description", "description"),
                    ("notes", "notes"),
                    ("itemType", "item_type"),
                ]:
                    if field in data:
                        setattr(ci, attr, data[field])
                ci.save()
                return JsonResponse(serialize_council_item(ci, request.user))

            return JsonResponse(
                {"error": "ACCESS DENIED."},
                status=403,
            )

        # DELETE — own proposals in proposed status only
        if request.method == "DELETE":
            if (
                user_agency_name
                and ci.proposed_by == user_agency_name
                and ci.status == "proposed"
            ):
                ci.delete()
                return JsonResponse({"status": "Council item record terminated."})
            return JsonResponse(
                {"error": "ACCESS DENIED. Can only withdraw your own proposals in 'proposed' status."},
                status=403,
            )

    if request.method == "GET":
        return JsonResponse(serialize_council_item(ci, request.user))

    if request.method == "PUT":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid data stream."}, status=400)

        if "name" in data:
            ci.name = data["name"]
        if "itemType" in data:
            ci.item_type = data["itemType"]
        if "description" in data:
            ci.description = data["description"]
        if "status" in data:
            ci.status = data["status"]
        if "proposedBy" in data:
            ci.proposed_by = data["proposedBy"]
        if "notes" in data:
            ci.notes = data["notes"]
        if "order" in data:
            ci.order = data["order"]
        if "predictedVotes" in data and request.user.is_superuser:
            ci.predicted_votes = data["predictedVotes"]

        ci.save()
        _broadcast_council_item(ci)
        return JsonResponse(serialize_council_item(ci, request.user))

    if request.method == "DELETE":
        ci.delete()
        return JsonResponse({"status": "Council item record terminated."})


@login_required
@require_http_methods(["PUT"])
def api_council_reorder(request):
    """Bulk reorder council items. Admin or chairman fixer player."""
    denied = _require_fixer(request.user)
    if denied:
        return denied
    if not request.user.is_superuser:
        # Check the user's agency is chairman
        char_ids = set(
            request.user.characters.values_list("id", flat=True)
        )
        is_chairman = False
        if char_ids:
            for base in Base.objects.filter(
                agency__is_player_agency=True,
                agency__is_council_chairman=True,
            ).select_related("agency"):
                for ws in base.workspaces or []:
                    if (
                        ws.get("assignedType") == "character"
                        and ws.get("assignedTo") in char_ids
                    ):
                        is_chairman = True
                        break
                if is_chairman:
                    break
        if not is_chairman:
            return JsonResponse(
                {"error": "ACCESS DENIED. Chairman clearance required."},
                status=403,
            )

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid data stream."}, status=400)

    # data.items is [{id, order}, ...]
    items = data.get("items", [])
    for entry in items:
        CouncilItem.objects.filter(pk=entry["id"]).update(order=entry["order"])

    all_items = CouncilItem.objects.all()
    return JsonResponse(
        [serialize_council_item(ci, request.user) for ci in all_items], safe=False
    )


@login_required
@require_http_methods(["POST"])
def api_council_vote(request, pk):
    """Cast or update a vote on a council item. Body: {agencyId, vote}.

    Admin can vote for any council member agency.
    Players can only vote for their own agency (fixer class required).
    Item must be in 'voting' status.
    """
    denied = _require_fixer(request.user)
    if denied:
        return denied
    ci = get_object_or_404(CouncilItem, pk=pk)
    if ci.status != "voting":
        return JsonResponse(
            {"error": "Voting is only allowed on items in 'voting' status."},
            status=400,
        )

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid data stream."}, status=400)

    agency_id = data.get("agencyId")
    vote_value = data.get("vote")
    if vote_value not in ("for", "against", "abstain"):
        return JsonResponse({"error": "Vote must be 'for', 'against', or 'abstain'."}, status=400)

    agency = get_object_or_404(Agency, pk=agency_id)
    if not agency.is_council_member:
        return JsonResponse({"error": "Agency is not a council member."}, status=400)

    # Permission check: admin can vote for any agency, players only their own
    if not request.user.is_superuser:
        char_ids = set(
            request.user.characters.values_list("id", flat=True)
        )
        user_agency = None
        if char_ids:
            for base in Base.objects.filter(
                agency__is_player_agency=True
            ).select_related("agency"):
                for ws in base.workspaces or []:
                    if (
                        ws.get("assignedType") == "character"
                        and ws.get("assignedTo") in char_ids
                    ):
                        user_agency = base.agency
                        break
                if user_agency:
                    break
        if not user_agency or user_agency.id != agency.id:
            return JsonResponse(
                {"error": "ACCESS DENIED. You can only vote for your own agency."},
                status=403,
            )

    CouncilVote.objects.update_or_create(
        council_item=ci,
        agency=agency,
        defaults={"vote": vote_value},
    )

    # Auto-transition: if all present members have voted, resolve the vote
    total_present = Agency.objects.filter(
        is_council_member=True, is_council_present=True
    ).count()
    total_voted = ci.votes.count()
    if total_present > 0 and total_voted >= total_present:
        # Build the final record and determine outcome
        record = build_vote_record(ci)
        result = record["tally"]["result"]
        ci.vote_record = record
        if result in ("passed", "passed_chairman"):
            ci.status = "active"
        elif result in ("failed", "failed_chairman"):
            ci.status = "repealed"
        # tied or no_quorum stays in voting (shouldn't happen if all voted)
        ci.save()

    # Return updated item with votes and broadcast to all clients
    ci.refresh_from_db()
    _broadcast_council_item(ci)
    return JsonResponse(serialize_council_item(ci, request.user))


# ---------------------------------------------------------------------------
# API views — Council Membership (superuser only)
# ---------------------------------------------------------------------------


@login_required
@require_http_methods(["GET"])
def api_council_members(request):
    """GET: list all agencies that are council members, with chairman info."""
    members = Agency.objects.filter(is_council_member=True).order_by(
        "-is_council_chairman", "name"
    )
    data = [
        {
            "id": a.id,
            "name": a.name,
            "isCouncilChairman": a.is_council_chairman,
            "isPlayerAgency": a.is_player_agency,
            "isPresent": a.is_council_present,
        }
        for a in members
    ]
    return JsonResponse(data, safe=False)


@login_required
@require_http_methods(["POST"])
def api_council_set_chairman(request, pk):
    """Set an agency as the council chairman. Clears any previous chairman."""
    if not request.user.is_superuser:
        return JsonResponse(
            {"error": "ACCESS DENIED. Administrator clearance required."}, status=403
        )
    agency = get_object_or_404(Agency, pk=pk)
    if not agency.is_council_member:
        return JsonResponse(
            {"error": "Agency must be a council member first."}, status=400
        )
    # Clear existing chairman
    Agency.objects.filter(is_council_chairman=True).update(is_council_chairman=False)
    agency.is_council_chairman = True
    agency.save()
    return JsonResponse({"status": "Chairman designation updated.", "agencyId": agency.id})


@login_required
@require_http_methods(["POST"])
def api_council_toggle_presence(request, pk):
    """Toggle an agency's council presence. Chairman fixer or admin only."""
    denied = _require_fixer(request.user)
    if denied:
        return denied
    if not request.user.is_superuser:
        # Check if user is chairman
        char_ids = set(
            request.user.characters.values_list("id", flat=True)
        )
        is_chairman = False
        if char_ids:
            for base in Base.objects.filter(
                agency__is_player_agency=True,
                agency__is_council_chairman=True,
            ).select_related("agency"):
                for ws in base.workspaces or []:
                    if (
                        ws.get("assignedType") == "character"
                        and ws.get("assignedTo") in char_ids
                    ):
                        is_chairman = True
                        break
                if is_chairman:
                    break
        if not is_chairman:
            return JsonResponse(
                {"error": "ACCESS DENIED. Chairman clearance required."},
                status=403,
            )

    agency = get_object_or_404(Agency, pk=pk)
    if not agency.is_council_member:
        return JsonResponse(
            {"error": "Agency is not a council member."}, status=400
        )
    agency.is_council_present = not agency.is_council_present
    agency.save()
    return JsonResponse({
        "id": agency.id,
        "name": agency.name,
        "isPresent": agency.is_council_present,
    })


def _apply_changes(agency, changes):
    """Apply proposed_changes dict to agency fields."""
    field_map = {
        "name": "name",
        "alliance": "alliance",
        "motto": "motto",
        "headquarters": "headquarters",
        "notes": "notes",
        "integrity": "integrity",
        "experience": "experience",
        "attributes": "attributes",
        "specializations": "specializations",
        "merits": "merits",
        "flaws": "flaws",
        "assets": "assets",
        "fleet": "fleet",
        "conditions": "conditions",
        "projects": "projects",
        "history": "history",
    }

    for key, value in changes.items():
        model_field = field_map.get(key)
        if model_field:
            setattr(agency, model_field, value)


# ---------------------------------------------------------------------------
# Page view — Base Configuration Settings
# ---------------------------------------------------------------------------


@login_required
def base_config_page(request):
    """Base configuration settings page. Superuser only."""
    if not request.user.is_superuser:
        return JsonResponse(
            {"error": "ACCESS DENIED. Administrator clearance required."}, status=403
        )
    return render(request, "agencies/base_config.html")


# ---------------------------------------------------------------------------
# API views — Base Configuration (singleton, superuser only)
# ---------------------------------------------------------------------------


@login_required
@require_http_methods(["GET", "PUT"])
def api_base_config(request):
    """GET: retrieve base config. PUT: update base config. Admin only."""
    if not request.user.is_superuser:
        return JsonResponse(
            {"error": "ACCESS DENIED. Administrator clearance required."}, status=403
        )

    config = BaseConfig.load()

    if request.method == "GET":
        return JsonResponse(serialize_base_config(config))

    # PUT
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid data stream."}, status=400)

    if "locationTypes" in data:
        config.location_types = data["locationTypes"]
    if "locationMerits" in data:
        config.location_merits = data["locationMerits"]
    if "facilityTypes" in data:
        config.facility_types = data["facilityTypes"]
    if "equipmentTypes" in data:
        config.equipment_types = data["equipmentTypes"]

    config.save()
    return JsonResponse(serialize_base_config(config))


# ---------------------------------------------------------------------------
# API views — Agency Bases (CRUD, superuser only)
# ---------------------------------------------------------------------------


@login_required
@require_http_methods(["GET", "POST"])
def api_agency_base_list(request, pk):
    """GET: list bases for an agency. POST: create a new base. Admin only."""
    agency = get_object_or_404(Agency, pk=pk)

    if request.method == "GET":
        bases = agency.bases.all() if request.user.is_superuser else agency.bases.filter(is_hidden=False)
        data = [serialize_base(b, is_admin=request.user.is_superuser) for b in bases]
        return JsonResponse(data, safe=False)

    # POST — admin only
    if not request.user.is_superuser:
        return JsonResponse(
            {"error": "ACCESS DENIED. Administrator clearance required."}, status=403
        )

    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        body = {}

    base = Base.objects.create(
        agency=agency,
        name=body.get("name", "NEW BASE"),
        location_type=body.get("locationType", ""),
        merits=body.get("merits", []),
        facilities=body.get("facilities", []),
        workspaces=body.get("workspaces", []),
        equipment=body.get("equipment", []),
        notes=body.get("notes", ""),
        is_hidden=bool(body.get("isHidden", False)),
        latitude=body.get("latitude"),
        longitude=body.get("longitude"),
    )
    return JsonResponse(serialize_base(base, is_admin=True), status=201)


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
def api_agency_base_detail(request, pk, base_id):
    """GET/PUT/DELETE a single base.

    Players can PUT additive changes (add facilities, merits, equipment, set location type).
    Only superusers can remove items, delete bases, or change admin fields.
    """
    base = get_object_or_404(Base, pk=base_id, agency_id=pk)
    is_admin = request.user.is_superuser

    if request.method == "GET":
        if base.is_hidden and not is_admin:
            return JsonResponse(
                {"error": "ACCESS DENIED. Base record not found."}, status=404
            )
        return JsonResponse(serialize_base(base, is_admin=is_admin))

    if request.method == "DELETE":
        if not is_admin:
            return JsonResponse({"error": "ACCESS DENIED."}, status=403)
        base.delete()
        return JsonResponse({"status": "Base record terminated."})

    # PUT — compatibility shim. Historical contract: a single PUT could
    # mutate any subset of base fields in one request (used by the legacy
    # frontend and the MCP ``update_base`` tool). We now route each provided
    # field through the per-section handler so the new authorization rules
    # (no silent issubset drop — explicit 403 on illegal removals) apply
    # uniformly. The per-base version is bumped once per affected section.
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid data stream."}, status=400)

    # Mapping from legacy PUT body keys to the new section_key. The PUT body
    # uses both `locationType` and the new `location` alias; the section
    # writers accept either.
    field_to_section = [
        ("name", "name"),
        ("locationType", "location"),
        ("location", "location"),
        ("merits", "merits"),
        ("facilities", "facilities"),
        ("workspaces", "workspaces"),
        ("equipment", "equipment"),
        ("departments", "departments"),
        ("notes", "notes"),
        ("isHidden", "hidden"),
        ("hidden", "hidden"),
        ("hiddenSections", "classified"),
        ("classified", "classified"),
    ]

    # ``geo`` is special: the writer reads both lat and long from the same
    # payload. We collapse them into a single section apply.
    has_geo = "latitude" in data or "longitude" in data

    # Run all writes inside one atomic transaction so a partial failure on a
    # multi-field PUT doesn't leave the base half-updated.
    sections_touched = set()
    with transaction.atomic():
        agency = Agency.objects.select_for_update().get(pk=pk)
        base = Base.objects.select_for_update().get(pk=base_id, agency_id=pk)
        if base.is_hidden and not is_admin:
            return JsonResponse(
                {"error": "ACCESS DENIED. Base record not found."}, status=404
            )

        update_fields = {"version", "updated_at"}
        for body_key, section_key in field_to_section:
            if body_key not in data or section_key in sections_touched:
                continue
            handler = _BASE_SECTION_HANDLERS[section_key]
            write_fn, fields = handler
            err = write_fn(request, agency, base, data)
            if err is not None:
                # Roll back by raising — transaction.atomic() will discard.
                # We capture the response to return outside the with block
                # so the rollback is honored.
                return err
            sections_touched.add(section_key)
            update_fields.update(fields)

        if has_geo:
            err = _write_base_geo(request, agency, base, data)
            if err is not None:
                return err
            sections_touched.add("geo")
            update_fields.update(("latitude", "longitude"))

        if sections_touched:
            base.version = (base.version or 0) + 1
            base.save(update_fields=list(update_fields))
        else:
            # Nothing changed — still call save() to update updated_at? No,
            # match legacy behavior of writing on PUT regardless.
            base.save()

    return JsonResponse(serialize_base(base, is_admin=is_admin))


@login_required
@require_http_methods(["POST"])
def api_sweep_condition(request, pk, condition_id):
    """Sweep & Clear a condition. Anyone with Computer skill can roll."""
    from agencies.models import Agency, AgencyCondition
    from comms.dice import roll_dice

    agency = get_object_or_404(Agency, pk=pk)
    condition = get_object_or_404(AgencyCondition, pk=condition_id, agency_id=pk, is_active=True)

    if agency.sweep_pool <= 0 and not request.user.is_superuser:
        return JsonResponse({"error": "No Sweep & Clear pool available. GM must allocate."}, status=400)

    # Get actor's stats — need Computer skill
    from characters.models import Character
    char = Character.objects.filter(owner=request.user).first()
    if not char and not request.user.is_superuser:
        return JsonResponse({"error": "No character found."}, status=400)

    if request.user.is_superuser and not agency.is_player_agency:
        # NPC agency — use best dossier
        from npcs.models import NPC
        best_pool = 0
        for npc in NPC.objects.filter(agency=agency, is_npc_dossier=True):
            comp = npc.skills.get("mental", {}).get("Computer", 0)
            if comp <= 0:
                continue
            p = npc.attributes.get("power", {}).get("mental", 1) + comp
            for nm in npc.npc_merits.select_related("merit").all():
                if nm.merit.name.lower() in ("computer aptitude", "rapid processing"):
                    p += 2
            best_pool = max(best_pool, p)
        pool = best_pool if best_pool > 0 else 10
    elif request.user.is_superuser:
        pool = 10
    else:
        computer = char.skills.get("mental", {}).get("Computer", 0)
        if computer <= 0:
            return JsonResponse({"error": "Computer skill required for Sweep & Clear."}, status=400)
        intelligence = char.attributes.get("power", {}).get("mental", 1)
        pool = intelligence + computer
        for cm in char.character_merits.select_related("merit").all():
            if cm.merit.name.lower() in ("computer aptitude", "rapid processing"):
                pool += 2
        # Mental load penalty
        pool -= char.mental_load

    result = roll_dice(pool)
    condition.sweep_progress += result.successes

    # Deduct 1 from agency sweep pool
    if agency.sweep_pool > 0:
        agency.sweep_pool -= 1
        agency.save(update_fields=["sweep_pool"])

    cleared = condition.sweep_progress >= condition.difficulty
    if cleared:
        condition.is_active = False

    condition.save(update_fields=["sweep_progress", "is_active"])

    return JsonResponse({
        "successes": result.successes,
        "rolls": result.rolls,
        "sweepProgress": condition.sweep_progress,
        "difficulty": condition.difficulty,
        "cleared": cleared,
        "sweepPoolRemaining": agency.sweep_pool,
    })


@login_required
def api_condition_detail(request, pk, condition_id):
    """GET: condition detail. PUT: GM updates sweep pool."""
    from agencies.models import AgencyCondition

    condition = get_object_or_404(AgencyCondition, pk=condition_id, agency_id=pk)

    if request.method == "GET":
        return JsonResponse({
            "id": condition.id,
            "type": condition.condition_type,
            "description": condition.description,
            "difficulty": condition.difficulty,
            "sweepPool": condition.sweep_pool,
            "sweepProgress": condition.sweep_progress,
            "isActive": condition.is_active,
        })

    if request.method == "PUT":
        if not request.user.is_superuser:
            return JsonResponse({"error": "Forbidden"}, status=403)
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        if "sweepPool" in data:
            from agencies.models import Agency
            agency = get_object_or_404(Agency, pk=pk)
            agency.sweep_pool = int(data["sweepPool"])
            agency.save(update_fields=["sweep_pool"])
        if "isActive" in data:
            condition.is_active = bool(data["isActive"])
            condition.save(update_fields=["is_active"])
        return JsonResponse({"status": "ok"})

    return JsonResponse({"error": "Method not allowed"}, status=405)


@login_required
@require_http_methods(["POST"])
def api_dark_grants(request, pk, project_index):
    """Activate Dark Grants on a fringe project. Science class only."""
    import random

    agency = get_object_or_404(Agency, pk=pk)

    # Check science class or admin
    from characters.models import Character
    char = Character.objects.filter(owner=request.user).first()
    is_science = request.user.is_superuser or (char and char.character_class == "science")
    if not is_science:
        return JsonResponse({"error": "Science class required."}, status=403)

    # Check pulling string
    has_dark_grants = False
    if request.user.is_superuser:
        has_dark_grants = True
    elif char:
        for cps in char.character_pulling_strings.select_related("pulling_string").all():
            if cps.pulling_string.name.lower() == "dark grants":
                has_dark_grants = True
                break
    if not has_dark_grants:
        return JsonResponse({"error": "Dark Grants pulling string required."}, status=403)

    # Validate project
    projects = agency.projects or []
    if project_index < 0 or project_index >= len(projects):
        return JsonResponse({"error": "Invalid project index."}, status=400)

    project = projects[project_index]
    if not isinstance(project, dict):
        return JsonResponse({"error": "Invalid project data."}, status=400)
    if not project.get("fringe"):
        return JsonResponse({"error": "Dark Grants can only be activated on fringe projects."}, status=400)
    if project.get("darkGrantsLevel"):
        return JsonResponse({"error": "Dark Grants already active on this project."}, status=400)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    level = int(body.get("level", 0))
    if level < 1 or level > 3:
        return JsonResponse({"error": "Level must be 1-3."}, status=400)

    # Roll for agency involvement: 1d10 per level, each 1-3 = an agency linked
    linked_agencies = []
    rolls = []
    # Get all NPC agencies (excluding player agency)
    npc_agencies = list(Agency.objects.filter(is_player_agency=False, is_hidden=False).values_list("id", "name"))
    random.shuffle(npc_agencies)

    thresholds = {1: 9, 2: 14, 3: 23}
    for i in range(level):
        die = random.randint(1, 100)
        rolls.append(die)
        if die <= thresholds.get(level, 9) and npc_agencies:
            # Pick an agency that isn't already linked
            for ag_id, ag_name in npc_agencies:
                if ag_id not in [la["id"] for la in linked_agencies]:
                    linked_agencies.append({"id": ag_id, "name": ag_name})
                    break

    # Update project
    project["darkGrantsLevel"] = level
    project["darkGrantsAgencies"] = linked_agencies
    projects[project_index] = project
    agency.projects = projects
    agency.save(update_fields=["projects"])

    return JsonResponse({
        "level": level,
        "bonusDice": level,
        "rolls": rolls,
        "linkedAgencies": linked_agencies,
        "message": f"Dark Grants level {level} activated. +{level} permanent dice to completion rolls."
            + (f" WARNING: {len(linked_agencies)} agency(ies) now linked to this project: {', '.join(a['name'] for a in linked_agencies)}" if linked_agencies else " No agencies linked — funding is clean."),
    })


@login_required
@require_http_methods(["POST"])
def api_live_testing(request, pk, project_index):
    """Activate live testing on a fringe project. Science class only."""
    import random

    agency = get_object_or_404(Agency, pk=pk)

    from characters.models import Character
    char = Character.objects.filter(owner=request.user).first()
    is_science = request.user.is_superuser or (char and char.character_class == "science")
    if not is_science:
        return JsonResponse({"error": "Science class required."}, status=403)

    projects = agency.projects or []
    if project_index < 0 or project_index >= len(projects):
        return JsonResponse({"error": "Invalid project index."}, status=400)

    project = projects[project_index]
    if not isinstance(project, dict):
        return JsonResponse({"error": "Invalid project data."}, status=400)
    if not project.get("fringe"):
        return JsonResponse({"error": "Live testing only on fringe projects."}, status=400)
    if project.get("liveTestingLevel"):
        return JsonResponse({"error": "Live testing already active on this project."}, status=400)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    level = body.get("level", "")
    valid_levels = {
        "small_animals": {"dice": 1, "mental_risk": 5, "integrity_risk": 0, "label": "Small Animals"},
        "large_animals": {"dice": 2, "mental_risk": 9, "integrity_risk": 0, "label": "Large Animals"},
        "human":         {"dice": 5, "mental_risk": 23, "integrity_risk": 17, "label": "Human Testing"},
        "off_books":     {"dice": 5, "mental_risk": 23, "integrity_risk": 0, "label": "Off the Books Human Testing"},
    }

    if level not in valid_levels:
        return JsonResponse({"error": "Invalid level. Choose: small_animals, large_animals, human, off_books"}, status=400)

    config = valid_levels[level]

    # Off the books requires the merit
    if level == "off_books":
        has_merit = False
        if request.user.is_superuser:
            has_merit = True
        elif char:
            for cm in char.character_merits.select_related("merit").all():
                if "off the books" in cm.merit.name.lower():
                    has_merit = True
                    break
        if not has_merit:
            return JsonResponse({"error": "Off the Books merit required."}, status=403)

    # Roll for consequences
    mental_roll = random.randint(1, 100)
    integrity_roll = random.randint(1, 100)
    mental_damage = mental_roll <= config["mental_risk"]
    integrity_loss = config["integrity_risk"] > 0 and integrity_roll <= config["integrity_risk"]

    # Find project owner character for mental load
    owner_name = project.get("player", "")
    messages = []

    if mental_damage:
        # Find character by name and add mental load
        owner_char = Character.objects.filter(name=owner_name).first()
        if owner_char:
            owner_char.mental_load = (owner_char.mental_load or 0) + 1
            owner_char.save(update_fields=["mental_load"])
            messages.append(owner_name + " takes 1 mental load damage (rolled " + str(mental_roll) + "/" + str(config["mental_risk"]) + "%).")
        else:
            messages.append("Mental load damage triggered but could not find character " + owner_name + ".")
    else:
        messages.append("No mental load damage (rolled " + str(mental_roll) + ", needed <=" + str(config["mental_risk"]) + "%).")

    if integrity_loss:
        agency.integrity = max(0, (agency.integrity or 0) - 1)
        agency.save(update_fields=["integrity"])
        messages.append("Agency loses 1 integrity point (rolled " + str(integrity_roll) + "/" + str(config["integrity_risk"]) + "%).")
    elif config["integrity_risk"] > 0:
        messages.append("No integrity loss (rolled " + str(integrity_roll) + ", needed <=" + str(config["integrity_risk"]) + "%).")

    # Update project
    project["liveTestingLevel"] = level
    project["liveTestingLabel"] = config["label"]
    project["liveTestingDice"] = config["dice"]
    projects[project_index] = project
    agency.projects = projects
    agency.save(update_fields=["projects"])

    return JsonResponse({
        "level": level,
        "label": config["label"],
        "bonusDice": config["dice"],
        "mentalDamage": mental_damage,
        "integrityLoss": integrity_loss,
        "messages": messages,
        "message": config["label"] + " activated. +" + str(config["dice"]) + " permanent dice.\n" + "\n".join(messages),
    })


@login_required
@require_http_methods(["POST"])
def api_stimulants(request, pk, project_index):
    """Administer stimulant cocktail to a fringe project. Science class only."""
    import random

    agency = get_object_or_404(Agency, pk=pk)

    from characters.models import Character
    char = Character.objects.filter(owner=request.user).first()
    is_science = request.user.is_superuser or (char and char.character_class == "science")
    if not is_science:
        return JsonResponse({"error": "Science class required."}, status=403)

    projects = agency.projects or []
    if project_index < 0 or project_index >= len(projects):
        return JsonResponse({"error": "Invalid project index."}, status=400)

    project = projects[project_index]
    if not isinstance(project, dict):
        return JsonResponse({"error": "Invalid project data."}, status=400)
    if not project.get("fringe"):
        return JsonResponse({"error": "Stimulants only on fringe projects."}, status=400)
    if project.get("stimulantLocked"):
        return JsonResponse({"error": "Stimulant cocktail already active. GM must unlock first."}, status=400)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    selected = body.get("stimulants", [])
    if not selected or not isinstance(selected, list):
        return JsonResponse({"error": "Select at least one stimulant."}, status=400)

    STIMULANTS = {
        "cocaine":  {"dice": 2, "base_risk": 15, "label": "Modified Cocaine",
                     "fail_mental": 1, "fail_bashing": 0, "fail_completion": 0},
        "lsd":      {"dice": 3, "base_risk": 20, "label": "Modified LSD",
                     "fail_mental": 2, "fail_bashing": 0, "fail_completion": 0},
        "shrooms":  {"dice": 2, "base_risk": 10, "label": "Modified Shrooms",
                     "fail_mental": 1, "fail_bashing": 0, "fail_completion": -1},
        "venom":    {"dice": 4, "base_risk": 25, "label": "Modified Exotic Animal Venom",
                     "fail_mental": 2, "fail_bashing": 1, "fail_completion": 0},
    }

    valid = [s for s in selected if s in STIMULANTS]
    if not valid:
        return JsonResponse({"error": "No valid stimulants selected."}, status=400)

    stack_penalty = (len(valid) - 1) * 10  # +10% per extra substance
    total_dice = 0
    results = []
    total_mental = 0
    total_bashing = 0
    total_completion_loss = 0

    for stim_key in valid:
        cfg = STIMULANTS[stim_key]
        total_dice += cfg["dice"]
        risk = cfg["base_risk"] + stack_penalty
        roll = random.randint(1, 100)
        failed = roll <= risk

        result = {
            "stimulant": stim_key,
            "label": cfg["label"],
            "dice": cfg["dice"],
            "risk": risk,
            "roll": roll,
            "failed": failed,
        }

        if failed:
            total_mental += cfg["fail_mental"]
            total_bashing += cfg["fail_bashing"]
            total_completion_loss += abs(cfg["fail_completion"])
            result["effects"] = []
            if cfg["fail_mental"]:
                result["effects"].append("Mental load +" + str(cfg["fail_mental"]))
            if cfg["fail_bashing"]:
                result["effects"].append("Bashing damage +" + str(cfg["fail_bashing"]))
            if cfg["fail_completion"]:
                result["effects"].append("Completion -" + str(abs(cfg["fail_completion"])))

        results.append(result)

    # Apply effects to project owner
    owner_name = project.get("player", "")
    owner_char = Character.objects.filter(name=owner_name).first()
    effect_messages = []

    if total_mental > 0 and owner_char:
        owner_char.mental_load = (owner_char.mental_load or 0) + total_mental
        owner_char.save(update_fields=["mental_load"])
        effect_messages.append(owner_name + " takes " + str(total_mental) + " mental load.")

    if total_bashing > 0 and owner_char:
        health = owner_char.health or {"bashing": 0, "lethal": 0, "aggravated": 0}
        health["bashing"] = health.get("bashing", 0) + total_bashing
        owner_char.health = health
        owner_char.save(update_fields=["health"])
        effect_messages.append(owner_name + " takes " + str(total_bashing) + " bashing damage.")

    if total_completion_loss > 0:
        old_score = int(project.get("completionScore", 0))
        project["completionScore"] = max(0, old_score - total_completion_loss)
        effect_messages.append("Completion reduced by " + str(total_completion_loss) + ".")

    # Lock the project with stimulant state
    project["stimulants"] = valid
    project["stimulantDice"] = total_dice
    project["stimulantLocked"] = True
    project["stimulantResults"] = results
    projects[project_index] = project
    agency.projects = projects
    agency.save(update_fields=["projects"])

    any_failed = any(r["failed"] for r in results)

    return JsonResponse({
        "totalDice": total_dice,
        "stimulants": [STIMULANTS[s]["label"] for s in valid],
        "stackPenalty": stack_penalty,
        "results": results,
        "effects": effect_messages,
        "anyFailed": any_failed,
        "message": "Stimulant cocktail administered. +" + str(total_dice) + " dice for next completion roll."
            + (" Side effects occurred." if any_failed else " No side effects.")
            + " Project locked until GM unlocks.",
    })


@login_required
@require_http_methods(["POST"])
def api_stimulants_unlock(request, pk, project_index):
    """GM unlocks a stimulant-locked project after completion roll."""
    if not request.user.is_superuser:
        return JsonResponse({"error": "GM only."}, status=403)

    agency = get_object_or_404(Agency, pk=pk)
    projects = agency.projects or []
    if project_index < 0 or project_index >= len(projects):
        return JsonResponse({"error": "Invalid project index."}, status=400)

    project = projects[project_index]
    if not isinstance(project, dict):
        return JsonResponse({"error": "Invalid project data."}, status=400)

    project.pop("stimulants", None)
    project.pop("stimulantDice", None)
    project.pop("stimulantLocked", None)
    project.pop("stimulantResults", None)
    projects[project_index] = project
    agency.projects = projects
    agency.save(update_fields=["projects"])

    return JsonResponse({"status": "unlocked"})


@login_required
@require_http_methods(["POST"])
def api_fringe_effect(request, pk, project_index):
    """Activate a new fringe effect on a fringe project. Science class only."""
    import random

    agency = get_object_or_404(Agency, pk=pk)

    from characters.models import Character
    char = Character.objects.filter(owner=request.user).first()
    is_science = request.user.is_superuser or (char and char.character_class == "science")
    if not is_science:
        return JsonResponse({"error": "Science class required."}, status=403)

    projects = agency.projects or []
    if project_index < 0 or project_index >= len(projects):
        return JsonResponse({"error": "Invalid project index."}, status=400)

    project = projects[project_index]
    if not isinstance(project, dict):
        return JsonResponse({"error": "Invalid project data."}, status=400)
    if not project.get("fringe"):
        return JsonResponse({"error": "Fringe effects only on fringe projects."}, status=400)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    effect = body.get("effect", "")

    # --- BLACK MARKET TECH (+2 dice, 15% tracker → agency linkage) ---
    if effect == "black_market_tech":
        if project.get("blackMarketTech"):
            return JsonResponse({"error": "Black Market Tech already active."}, status=400)

        roll = random.randint(1, 100)
        linked_agencies = []
        if roll <= 15:
            npc_agencies = list(Agency.objects.filter(
                is_player_agency=False, is_hidden=False
            ).values_list("id", "name"))
            random.shuffle(npc_agencies)
            if npc_agencies:
                linked_agencies.append({"id": npc_agencies[0][0], "name": npc_agencies[0][1]})

        project["blackMarketTech"] = True
        project["blackMarketTechDice"] = 2
        project["blackMarketTechAgencies"] = linked_agencies
        projects[project_index] = project
        agency.projects = projects
        agency.save(update_fields=["projects"])

        msg = "Black Market Tech activated. +2 permanent dice."
        if linked_agencies:
            msg += " WARNING: Equipment came with a tracker! " + linked_agencies[0]["name"] + " is now linked."
        else:
            msg += " Equipment is clean — no trackers detected."

        return JsonResponse({
            "dice": 2, "roll": roll, "linkedAgencies": linked_agencies, "message": msg,
        })

    # --- GENE MANIPULATION (+3 dice, 18% containment breach) ---
    elif effect == "gene_manipulation":
        if project.get("geneManipulation"):
            return JsonResponse({"error": "Gene Manipulation already active."}, status=400)

        roll = random.randint(1, 100)
        breach = roll <= 18

        project["geneManipulation"] = True
        project["geneManipulationDice"] = 3
        project["geneManipulationBreach"] = breach
        projects[project_index] = project
        agency.projects = projects
        agency.save(update_fields=["projects"])

        msg = "Gene Manipulation activated. +3 permanent dice."
        if breach:
            msg += " CONTAINMENT BREACH! (rolled " + str(roll) + "/18%). GM determines narrative consequences."
        else:
            msg += " Containment held (rolled " + str(roll) + ", needed <=18%)."

        return JsonResponse({
            "dice": 3, "roll": roll, "breach": breach, "message": msg,
        })

    # --- NEURAL INTERFACE (+4 dice, 30% ML+2, 5% permanent -1 mental attribute) ---
    elif effect == "neural_interface":
        if project.get("neuralInterface"):
            return JsonResponse({"error": "Neural Interface already active for this roll."}, status=400)

        ml_roll = random.randint(1, 100)
        attr_roll = random.randint(1, 100)
        ml_damage = ml_roll <= 30
        attr_damage = attr_roll <= 5

        messages = []
        owner_name = project.get("player", "")
        owner_char = Character.objects.filter(name=owner_name).first()

        if ml_damage and owner_char:
            owner_char.mental_load = (owner_char.mental_load or 0) + 2
            owner_char.save(update_fields=["mental_load"])
            messages.append(owner_name + " takes 2 mental load (rolled " + str(ml_roll) + "/30%).")
        elif ml_damage:
            messages.append("Mental load triggered but could not find " + owner_name + ".")
        else:
            messages.append("No mental load (rolled " + str(ml_roll) + ", needed <=30%).")

        attr_damaged = None
        if attr_damage and owner_char:
            attrs = owner_char.attributes or {}
            attr_options = []
            power_mental = attrs.get("power", {}).get("mental", 1)
            finesse_mental = attrs.get("finesse", {}).get("mental", 1)
            resistance_mental = attrs.get("resistance", {}).get("mental", 1)
            if power_mental > 1:
                attr_options.append(("power", "mental", "Intelligence"))
            if finesse_mental > 1:
                attr_options.append(("finesse", "mental", "Wits"))
            if resistance_mental > 1:
                attr_options.append(("resistance", "mental", "Resolve"))

            if attr_options:
                chosen = random.choice(attr_options)
                attrs[chosen[0]][chosen[1]] = attrs[chosen[0]].get(chosen[1], 1) - 1
                owner_char.attributes = attrs
                owner_char.save(update_fields=["attributes"])
                attr_damaged = chosen[2]
                messages.append("PERMANENT DAMAGE: " + owner_name + "'s " + chosen[2] + " reduced by 1 (rolled " + str(attr_roll) + "/5%).")
            else:
                messages.append("Attribute damage triggered but all mental attributes at minimum.")
        elif attr_damage:
            messages.append("Attribute damage triggered but could not find " + owner_name + ".")
        else:
            messages.append("No permanent attribute damage (rolled " + str(attr_roll) + ", needed <=5%).")

        project["neuralInterface"] = True
        project["neuralInterfaceDice"] = 4
        project["neuralInterfaceMlDamage"] = 2 if ml_damage else 0
        project["neuralInterfaceAttrDamage"] = attr_damaged
        projects[project_index] = project
        agency.projects = projects
        agency.save(update_fields=["projects"])

        return JsonResponse({
            "dice": 4, "mlRoll": ml_roll, "attrRoll": attr_roll,
            "mlDamage": ml_damage, "attrDamage": attr_damaged,
            "messages": messages,
            "message": "Neural Interface activated. +4 permanent dice.\n" + "\n".join(messages),
        })

    # --- SLEEP DEPRIVATION MARATHON (+2 dice, 30% ML+1 to project owner) ---
    elif effect == "sleep_deprivation":
        if project.get("sleepDeprivation"):
            return JsonResponse({"error": "Sleep Deprivation Marathon already active for this roll."}, status=400)

        roll = random.randint(1, 100)
        ml_damage = roll <= 30
        messages = []

        if ml_damage:
            owner_name = project.get("player", "")
            owner_char = Character.objects.filter(name=owner_name).first()
            if owner_char:
                owner_char.mental_load = (owner_char.mental_load or 0) + 1
                owner_char.save(update_fields=["mental_load"])
                messages.append(owner_name + " takes 1 mental load (rolled " + str(roll) + "/30%).")
            else:
                messages.append("Mental load triggered but could not find " + owner_name + ".")
            messages.append("GM: Apply ML +1 to all other team members on this project.")
        else:
            messages.append("No mental load damage (rolled " + str(roll) + ", needed <=30%).")

        project["sleepDeprivation"] = True
        project["sleepDeprivationDice"] = 2
        project["sleepDeprivationMlDamage"] = ml_damage
        projects[project_index] = project
        agency.projects = projects
        agency.save(update_fields=["projects"])

        return JsonResponse({
            "dice": 2, "roll": roll, "mlDamage": ml_damage,
            "messages": messages,
            "message": "Sleep Deprivation Marathon activated. +2 permanent dice.\n" + "\n".join(messages),
        })

    # --- OVERCLOCKED EQUIPMENT (+3 dice, 25% facility level loss, select base) ---
    elif effect == "overclocked_equipment":
        if project.get("overclockedEquipment"):
            return JsonResponse({"error": "Overclocked Equipment already active."}, status=400)

        base_id = body.get("baseId")
        if not base_id:
            return JsonResponse({"error": "Select a base."}, status=400)

        base = Base.objects.filter(id=base_id, agency=agency).first()
        if not base:
            return JsonResponse({"error": "Base not found."}, status=400)

        # Verify the project owner has a workspace at this base
        owner_name = project.get("player", "")
        owner_char = Character.objects.filter(name=owner_name).first()
        has_workspace = False
        if owner_char:
            has_workspace = any(
                w.get("assignedType") == "character" and w.get("assignedTo") == owner_char.id
                for w in (base.workspaces or [])
            )
        if not has_workspace and not request.user.is_superuser:
            return JsonResponse({"error": "Project owner must have a workspace at this base."}, status=400)

        roll = random.randint(1, 100)
        destroyed = roll <= 25
        destroyed_info = None

        xp_lost = 0
        if destroyed:
            facilities = base.facilities or []
            if facilities:
                fac_idx = random.randint(0, len(facilities) - 1)
                fac = facilities[fac_idx]
                fac_key = fac.get("key", "unknown")
                old_level = fac.get("level", 1)
                if old_level > 1:
                    facilities[fac_idx]["level"] = old_level - 1
                    destroyed_info = {"baseName": base.name, "facilityKey": fac_key, "oldLevel": old_level, "newLevel": old_level - 1}
                else:
                    facilities.pop(fac_idx)
                    destroyed_info = {"baseName": base.name, "facilityKey": fac_key, "oldLevel": old_level, "newLevel": 0, "removed": True}
                base.facilities = facilities
                base.save(update_fields=["facilities"])

                # XP penalty: 3-7 XP subtracted from agency
                xp_lost = random.randint(3, 7)
                agency.experience = (agency.experience or 0) - xp_lost

                # Log the XP loss
                from .models import BaseXpLog
                BaseXpLog.objects.create(
                    agency=agency,
                    base=base,
                    amount=-xp_lost,
                    reason="Overclocked Equipment destroyed " + fac_key + " at " + base.name + " (fringe project: " + project.get("name", "") + ")",
                )

        project["overclockedEquipment"] = True
        project["overclockedEquipmentDice"] = 3
        project["overclockedEquipmentDestroyed"] = destroyed_info
        project["overclockedEquipmentBase"] = base.name
        project["overclockedEquipmentXpLost"] = xp_lost
        projects[project_index] = project
        agency.projects = projects
        save_fields = ["projects"]
        if xp_lost:
            save_fields.append("experience")
        agency.save(update_fields=save_fields)

        msg = "Overclocked Equipment activated. +3 permanent dice."
        if destroyed_info:
            msg += " EQUIPMENT DESTROYED: " + destroyed_info["facilityKey"] + " at " + base.name
            if destroyed_info.get("removed"):
                msg += " completely destroyed!"
            else:
                msg += " reduced from level " + str(destroyed_info["oldLevel"]) + " to " + str(destroyed_info["newLevel"]) + "."
            msg += " Agency loses " + str(xp_lost) + " XP."
        else:
            msg += " Equipment held (rolled " + str(roll) + ", needed <=25%)."

        return JsonResponse({
            "dice": 3, "roll": roll, "destroyed": destroyed_info, "xpLost": xp_lost, "message": msg,
        })

    # --- CHILD PRODIGY RECRUITMENT (+1 permanent, 15% integrity loss, costs 2 XP, creates NPC) ---
    elif effect == "child_prodigy":
        if project.get("childProdigy"):
            return JsonResponse({"error": "Child Prodigy already recruited."}, status=400)

        if agency.experience < 2:
            return JsonResponse({"error": "Insufficient XP. Need 2, have " + str(agency.experience) + "."}, status=400)

        roll = random.randint(1, 100)
        integrity_loss = roll <= 15

        # Deduct XP
        agency.experience -= 2

        if integrity_loss:
            agency.integrity = max(0, (agency.integrity or 0) - 1)

        # Create NPC dossier tagged as child prodigy
        from npcs.models import NPC
        npc = NPC.objects.create(
            agency=agency,
            name="Child Prodigy (" + project.get("name", "Unknown") + ")",
            is_npc_dossier=True,
            is_child_prodigy=True,
            state="active",
            created_by=request.user,
        )

        project["childProdigy"] = True
        project["childProdigyDice"] = 1
        project["childProdigyNpcId"] = npc.id
        project["childProdigyIntegrityLoss"] = integrity_loss
        projects[project_index] = project
        agency.projects = projects
        save_fields = ["projects", "experience"]
        if integrity_loss:
            save_fields.append("integrity")
        agency.save(update_fields=save_fields)

        msg = "Child Prodigy recruited. +1 permanent dice. 2 XP spent."
        if integrity_loss:
            msg += " Integrity loss! (rolled " + str(roll) + "/15%)."
        else:
            msg += " No integrity loss (rolled " + str(roll) + ", needed <=15%)."
        msg += " NPC '" + npc.name + "' added to dossier."

        return JsonResponse({
            "dice": 1, "roll": roll, "integrityLoss": integrity_loss,
            "npcId": npc.id, "npcName": npc.name, "message": msg,
        })

    # --- ASSIGN CHILD PRODIGY to a fringe project (+2 dice) ---
    elif effect == "assign_prodigy":
        if project.get("assignedProdigyId"):
            return JsonResponse({"error": "A prodigy is already assigned to this project."}, status=400)

        npc_id = body.get("npcId")
        if not npc_id:
            return JsonResponse({"error": "Select a child prodigy."}, status=400)

        from npcs.models import NPC
        npc = NPC.objects.filter(id=npc_id, agency=agency, is_child_prodigy=True).first()
        if not npc:
            return JsonResponse({"error": "Child prodigy not found."}, status=400)

        # Check prodigy isn't already assigned to another project
        for i, proj in enumerate(projects):
            if isinstance(proj, dict) and proj.get("assignedProdigyId") == npc_id and i != project_index:
                return JsonResponse({"error": npc.name + " is already assigned to " + proj.get("name", "another project") + "."}, status=400)

        project["assignedProdigyId"] = npc.id
        project["assignedProdigyName"] = npc.name
        project["assignedProdigyDice"] = 2
        projects[project_index] = project
        agency.projects = projects
        agency.save(update_fields=["projects"])

        return JsonResponse({
            "dice": 2, "npcId": npc.id, "npcName": npc.name,
            "message": npc.name + " assigned to " + project.get("name", "") + ". +2 dice to completion rolls.",
        })

    # --- UNASSIGN CHILD PRODIGY from a project ---
    elif effect == "unassign_prodigy":
        if not project.get("assignedProdigyId"):
            return JsonResponse({"error": "No prodigy assigned to this project."}, status=400)

        name = project.get("assignedProdigyName", "Prodigy")
        project.pop("assignedProdigyId", None)
        project.pop("assignedProdigyName", None)
        project.pop("assignedProdigyDice", None)
        projects[project_index] = project
        agency.projects = projects
        agency.save(update_fields=["projects"])

        return JsonResponse({"message": name + " unassigned from project."})

    return JsonResponse({"error": "Unknown effect: " + effect}, status=400)


@login_required
@require_http_methods(["POST"])
def api_complete_project(request, pk, project_index):
    """Complete a project: apply attribute effects and integrity modifier, log changes."""
    if not request.user.is_superuser:
        return JsonResponse({"error": "GM only."}, status=403)

    agency = get_object_or_404(Agency, pk=pk)
    projects = agency.projects or []
    if project_index < 0 or project_index >= len(projects):
        return JsonResponse({"error": "Invalid project index."}, status=400)

    project = projects[project_index]
    if not isinstance(project, dict):
        return JsonResponse({"error": "Invalid project data."}, status=400)
    if project.get("completed"):
        return JsonResponse({"error": "Project already completed."}, status=400)

    effects = project.get("completionEffects") or {}
    messages = []

    # Apply attribute changes
    attrs = agency.attributes or {}
    for change in (effects.get("attributeChanges") or []):
        cat = change.get("category", "")
        name = change.get("name", "")
        amount = int(change.get("value", 0))
        if not cat or not name or amount == 0:
            continue
        if cat not in attrs:
            attrs[cat] = {}
        old_val = attrs[cat].get(name, 0)
        attrs[cat][name] = old_val + amount
        AgencyStatLog.objects.create(
            agency=agency,
            stat_type="attribute",
            stat_path=cat + "." + name,
            amount=amount,
            reason="Project '" + project.get("name", "") + "' completed",
        )
        messages.append(name + " " + ("{:+d}".format(amount)) + " (was " + str(old_val) + ", now " + str(old_val + amount) + ")")

    agency.attributes = attrs

    # Apply integrity change
    integrity_change = int(effects.get("integrityChange", 0))
    if integrity_change != 0:
        old_int = agency.integrity or 0
        agency.integrity = old_int + integrity_change
        AgencyStatLog.objects.create(
            agency=agency,
            stat_type="integrity",
            stat_path="integrity",
            amount=integrity_change,
            reason="Project '" + project.get("name", "") + "' completed",
        )
        messages.append("Integrity " + ("{:+d}".format(integrity_change)) + " (was " + str(old_int) + ", now " + str(old_int + integrity_change) + ")")

    # Mark project completed and unassign NPCs
    project["completed"] = True
    project.pop("assignedNpcs", None)
    projects[project_index] = project
    agency.projects = projects
    agency.save(update_fields=["projects", "attributes", "integrity"])

    return JsonResponse({
        "messages": messages,
        "message": "Project '" + project.get("name", "") + "' completed." + ("\n" + "\n".join(messages) if messages else " No stat changes."),
    })


@login_required
@require_http_methods(["GET"])
def api_stat_logs(request, pk):
    """Return stat change logs for an agency."""
    agency = get_object_or_404(Agency, pk=pk)
    logs = AgencyStatLog.objects.filter(agency=agency)[:50]
    return JsonResponse({
        "logs": [
            {
                "id": log.id,
                "statType": log.stat_type,
                "statPath": log.stat_path,
                "amount": log.amount,
                "reason": log.reason,
                "date": log.created_at.isoformat(),
            }
            for log in logs
        ]
    })


@login_required
@require_http_methods(["POST"])
def api_project_roll(request, pk, project_index):
    """Player spends a roll allocation to make a completion roll on their project."""
    import random

    agency = get_object_or_404(Agency, pk=pk)

    from characters.models import Character
    char = Character.objects.filter(owner=request.user).first()

    projects = agency.projects or []
    if project_index < 0 or project_index >= len(projects):
        return JsonResponse({"error": "Invalid project index."}, status=400)

    project = projects[project_index]
    if not isinstance(project, dict):
        return JsonResponse({"error": "Invalid project data."}, status=400)

    # Check ownership — player can only roll on projects assigned to their character
    if not request.user.is_superuser:
        if not char or project.get("player") != char.name:
            return JsonResponse({"error": "You can only roll on your own projects."}, status=403)

    # Determine available rolls (per-character allocation)
    rolls_data = agency.project_rolls or {}
    char_name = char.name if char else ""
    personal = rolls_data.get(char_name, {})

    total_free = personal.get("free", 0) or 0
    total_spare = personal.get("spare", 0) or 0

    if total_free <= 0 and total_spare <= 0:
        return JsonResponse({"error": "No rolls available."}, status=400)

    # Determine roll type: free rolls first, then spare time
    roll_type = "free" if total_free > 0 else "spare"

    # Deduct the roll from character's allocation
    if roll_type == "free":
        personal["free"] = total_free - 1
    else:
        personal["spare"] = total_spare - 1
    rolls_data[char_name] = personal

    # Apply mental load for spare time rolls
    mental_damage = False
    if roll_type == "spare" and char:
        char.mental_load = (char.mental_load or 0) + 1
        char.save(update_fields=["mental_load"])
        mental_damage = True

    # Get dice pool from computed pool or default to 1
    pool_size = 1
    # Re-compute pool server-side
    from .serializers import _compute_project_dice_pool
    characters_by_name = {c.name: c for c in Character.objects.prefetch_related(
        "character_merits__merit", "character_pulling_strings__pulling_string"
    ).all()}
    bases_list = list(agency.bases.all())
    computed = _compute_project_dice_pool(project, agency, characters_by_name, bases_list)
    if computed:
        pool_size = max(computed["pool"], 1)

    # Check for auto-success merit activation
    auto_merit_name = None
    auto_successes = 0
    try:
        body = json.loads(request.body) if request.body else {}
        auto_merit_name = body.get("useAutoMerit")
    except (json.JSONDecodeError, AttributeError):
        pass

    if auto_merit_name and char:
        cm = char.character_merits.select_related("merit").filter(merit__name=auto_merit_name).first()
        if cm and cm.merit.effects.get("auto_success"):
            uses = char.merit_uses or {}
            used = uses.get(auto_merit_name, 0)
            if used < cm.rating:
                auto_successes = cm.rating
                uses[auto_merit_name] = used + 1
                char.merit_uses = uses
                char.save(update_fields=["merit_uses"])
            else:
                auto_merit_name = None  # No uses left
        else:
            auto_merit_name = None  # Not a valid auto-success merit

    # Roll dice (WoD 2.0: d10, 8+ = success, reroll threshold from config)
    reroll_threshold = int(project.get("rerollThreshold", 10) or 10)
    successes = 0
    rolls = []
    dice_left = pool_size
    while dice_left > 0:
        batch = []
        explosions = 0
        for _ in range(dice_left):
            die = random.randint(1, 10)
            batch.append(die)
            if die >= 8:
                successes += 1
            if die >= reroll_threshold:
                explosions += 1
        rolls.extend(batch)
        dice_left = explosions

    # Add auto-successes from merit
    successes += auto_successes

    # Add auto-successes from child prodigy (+2 per roll if assigned)
    prodigy_successes = 0
    if project.get("assignedProdigyId"):
        prodigy_successes = 2
        successes += prodigy_successes

    # Chance die if pool was 0 or less
    is_chance = pool_size <= 0
    is_dramatic_failure = is_chance and len(rolls) > 0 and rolls[0] == 1

    # Add successes to project completion
    old_score = int(project.get("completionScore", 0))
    project["completionScore"] = old_score + successes

    # Clear per-roll fringe effects (consumed on roll)
    for per_roll_key in ["stimulants", "stimulantDice", "stimulantLocked", "stimulantResults",
                         "neuralInterface", "neuralInterfaceDice", "neuralInterfaceMlDamage", "neuralInterfaceAttrDamage",
                         "sleepDeprivation", "sleepDeprivationDice", "sleepDeprivationMlDamage"]:
        project.pop(per_roll_key, None)

    projects[project_index] = project
    agency.project_rolls = rolls_data
    agency.projects = projects
    agency.save(update_fields=["projects", "project_rolls"])

    dice_successes = successes - auto_successes - prodigy_successes
    msg = roll_type.replace("_", " ").title() + " roll: " + str(pool_size) + " dice → " + str(dice_successes) + " successes."
    if auto_successes > 0:
        msg += " +" + str(auto_successes) + " auto (" + auto_merit_name + ")."
    if prodigy_successes > 0:
        msg += " +" + str(prodigy_successes) + " auto (Child Prodigy)."
    if auto_successes > 0 or prodigy_successes > 0:
        msg += " Total: " + str(successes) + " successes."
    if successes >= 5:
        msg += " EXCEPTIONAL SUCCESS!"
    if mental_damage:
        msg += " " + char_name + " takes 1 mental load."
    msg += " Completion: " + str(old_score) + " → " + str(project["completionScore"]) + "."

    # Log the roll
    try:
        ProjectRollLog.objects.create(
            agency=agency,
            project_index=project_index,
            project_name=project.get("name", ""),
            character_name=char_name,
            roll_type=roll_type,
            pool=pool_size,
            rolls=rolls,
            successes=successes,
            auto_successes=auto_successes + prodigy_successes,
            auto_merit=(auto_merit_name or "") + (" + Child Prodigy" if prodigy_successes > 0 else "") if (auto_successes > 0 or prodigy_successes > 0) else "",
            mental_damage=mental_damage,
            old_score=old_score,
            new_score=project["completionScore"],
            message=msg,
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Failed to log project roll")

    return JsonResponse({
        "rollType": roll_type,
        "pool": pool_size,
        "rolls": rolls,
        "successes": successes,
        "autoSuccesses": auto_successes + prodigy_successes,
        "autoMerit": (auto_merit_name or "") + (" + Child Prodigy" if prodigy_successes > 0 else "") if (auto_successes > 0 or prodigy_successes > 0) else None,
        "isChance": is_chance,
        "isDramaticFailure": is_dramatic_failure,
        "mentalDamage": mental_damage,
        "oldScore": old_score,
        "newScore": project["completionScore"],
        "message": msg,
    })


@login_required
@require_http_methods(["GET"])
def api_project_roll_log(request, pk, project_index):
    """Get roll log for a regular project."""
    agency = get_object_or_404(Agency, pk=pk)
    logs = ProjectRollLog.objects.filter(
        agency=agency, project_index=project_index, assignment__isnull=True,
    )[:50]
    data = [
        {
            "id": log.id,
            "characterName": log.character_name,
            "rollType": log.roll_type,
            "pool": log.pool,
            "rolls": log.rolls,
            "successes": log.successes,
            "autoSuccesses": log.auto_successes,
            "autoMerit": log.auto_merit or None,
            "mentalDamage": log.mental_damage,
            "oldScore": log.old_score,
            "newScore": log.new_score,
            "message": log.message,
            "rolledAt": log.rolled_at.isoformat(),
        }
        for log in logs
    ]
    return JsonResponse(data, safe=False)


@login_required
@require_http_methods(["POST"])
def api_ftl_meta(request, pk, assignment_id):
    """Update FTL assignment metadata: player, base, dice pool config, fringe, NPCs, etc."""
    agency = get_object_or_404(Agency, pk=pk)
    afp = AgencyFTLProject.objects.filter(id=assignment_id, agency=agency).first()
    if not afp:
        return JsonResponse({"error": "FTL assignment not found."}, status=404)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    # Direct field updates (admin only)
    if request.user.is_superuser:
        if "player" in body:
            afp.player = body["player"]
        if "baseId" in body:
            afp.base_id = body["baseId"] or None
            afp.base_name = body.get("baseName", "")

    # Metadata updates
    meta = afp.metadata or {}
    if "dicePoolConfig" in body:
        meta["dicePoolConfig"] = body["dicePoolConfig"]
    if "assignedNpcs" in body:
        meta["assignedNpcs"] = body["assignedNpcs"]
    if "completionEffects" in body:
        meta["completionEffects"] = body["completionEffects"]
    if "toggleFringe" in body and request.user.is_superuser:
        meta["fringe"] = not meta.get("fringe", False)
    if "rerollThreshold" in body and request.user.is_superuser:
        meta["rerollThreshold"] = int(body["rerollThreshold"])

    afp.metadata = meta
    afp.save()

    return JsonResponse({"status": "updated", "metadata": meta, "player": afp.player, "baseId": afp.base_id, "baseName": afp.base_name})


@login_required
@require_http_methods(["POST"])
def api_ftl_fringe_effect(request, pk, assignment_id):
    """Activate a fringe effect on an FTL project. Mirrors api_fringe_effect."""
    import random

    agency = get_object_or_404(Agency, pk=pk)
    afp = AgencyFTLProject.objects.filter(id=assignment_id, agency=agency).first()
    if not afp:
        return JsonResponse({"error": "FTL assignment not found."}, status=404)

    from characters.models import Character
    char = Character.objects.filter(owner=request.user).first()
    is_science = request.user.is_superuser or (char and char.character_class == "science")
    if not is_science:
        return JsonResponse({"error": "Science class required."}, status=403)

    meta = afp.metadata or {}
    if not meta.get("fringe"):
        return JsonResponse({"error": "Project must be marked as fringe first."}, status=400)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    effect = body.get("effect", "")

    # Build a fake project dict from metadata for reuse
    project = dict(meta)
    project["player"] = afp.player
    project["name"] = afp.ftl_project.name

    # Reuse the same fringe effect logic by calling the handler inline
    # Dark Grants
    if effect == "dark_grants":
        level = int(body.get("level", 0))
        if level < 1 or level > 3:
            return JsonResponse({"error": "Level must be 1-3."}, status=400)
        if meta.get("darkGrantsLevel"):
            return JsonResponse({"error": "Dark Grants already active."}, status=400)
        linked_agencies = []
        npc_agencies = list(Agency.objects.filter(is_player_agency=False, is_hidden=False).values_list("id", "name"))
        random.shuffle(npc_agencies)
        thresholds = {1: 9, 2: 14, 3: 23}
        rolls = []
        for i in range(level):
            die = random.randint(1, 100)
            rolls.append(die)
            if die <= thresholds.get(level, 9) and npc_agencies:
                for ag_id, ag_name in npc_agencies:
                    if ag_id not in [la["id"] for la in linked_agencies]:
                        linked_agencies.append({"id": ag_id, "name": ag_name})
                        break
        meta["darkGrantsLevel"] = level
        meta["darkGrantsAgencies"] = linked_agencies
        afp.metadata = meta
        afp.save()
        msg = "Dark Grants level " + str(level) + " activated. +" + str(level) + " permanent dice."
        if linked_agencies:
            msg += " WARNING: " + str(len(linked_agencies)) + " agency(ies) linked."
        return JsonResponse({"level": level, "rolls": rolls, "linkedAgencies": linked_agencies, "message": msg})

    # For other effects, store directly in metadata using same keys as regular projects
    SIMPLE_EFFECTS = {
        "black_market_tech": {"key": "blackMarketTech", "dice_key": "blackMarketTechDice", "dice": 2, "risk": 15, "risk_type": "agency"},
        "gene_manipulation": {"key": "geneManipulation", "dice_key": "geneManipulationDice", "dice": 3, "risk": 18, "risk_type": "breach"},
        "neural_interface": {"key": "neuralInterface", "dice_key": "neuralInterfaceDice", "dice": 4},
        "sleep_deprivation": {"key": "sleepDeprivation", "dice_key": "sleepDeprivationDice", "dice": 2},
    }

    if effect in SIMPLE_EFFECTS:
        cfg = SIMPLE_EFFECTS[effect]
        if meta.get(cfg["key"]):
            return JsonResponse({"error": "Already active."}, status=400)
        roll = random.randint(1, 100)
        meta[cfg["key"]] = True
        meta[cfg["dice_key"]] = cfg["dice"]
        afp.metadata = meta
        afp.save()
        return JsonResponse({"dice": cfg["dice"], "roll": roll, "message": effect.replace("_", " ").title() + " activated. +" + str(cfg["dice"]) + " dice."})

    if effect == "live_testing":
        level = body.get("level", "")
        valid_levels = {
            "small_animals": {"dice": 1, "label": "Small Animals"},
            "large_animals": {"dice": 2, "label": "Large Animals"},
            "human": {"dice": 5, "label": "Human Testing"},
            "off_books": {"dice": 5, "label": "Off the Books Human Testing"},
        }
        if level not in valid_levels:
            return JsonResponse({"error": "Invalid level."}, status=400)
        if meta.get("liveTestingLevel"):
            return JsonResponse({"error": "Already active."}, status=400)
        cfg = valid_levels[level]
        meta["liveTestingLevel"] = level
        meta["liveTestingLabel"] = cfg["label"]
        meta["liveTestingDice"] = cfg["dice"]
        afp.metadata = meta
        afp.save()
        return JsonResponse({"dice": cfg["dice"], "label": cfg["label"], "message": cfg["label"] + " activated. +" + str(cfg["dice"]) + " dice."})

    return JsonResponse({"error": "Unknown effect: " + effect}, status=400)


@login_required
@require_http_methods(["POST"])
def api_ftl_roll(request, pk, assignment_id):
    """Player rolls on an FTL project using their roll allocation."""
    import random

    agency = get_object_or_404(Agency, pk=pk)
    afp = AgencyFTLProject.objects.filter(id=assignment_id, agency=agency).first()
    if not afp:
        return JsonResponse({"error": "FTL assignment not found."}, status=404)

    from characters.models import Character
    char = Character.objects.filter(owner=request.user).first()
    char_name = char.name if char else ""

    if not request.user.is_superuser and afp.player != char_name:
        return JsonResponse({"error": "You can only roll on your own projects."}, status=403)

    # Check rolls
    rolls_data = agency.project_rolls or {}
    personal = rolls_data.get(char_name, {})
    total_free = personal.get("free", 0) or 0
    total_spare = personal.get("spare", 0) or 0

    if total_free <= 0 and total_spare <= 0:
        return JsonResponse({"error": "No rolls available."}, status=400)

    roll_type = "free" if total_free > 0 else "spare"
    if roll_type == "free":
        personal["free"] = total_free - 1
    else:
        personal["spare"] = total_spare - 1
    rolls_data[char_name] = personal

    mental_damage = False
    if roll_type == "spare" and char:
        char.mental_load = (char.mental_load or 0) + 1
        char.save(update_fields=["mental_load"])
        mental_damage = True

    # Compute pool
    pool_size = 1
    meta = afp.metadata or {}
    if meta.get("dicePoolConfig"):
        from .serializers import _compute_project_dice_pool
        fake_project = {"player": afp.player, "baseId": afp.base_id, "dicePoolConfig": meta.get("dicePoolConfig"), "assignedNpcs": meta.get("assignedNpcs", [])}
        for fk, _ in [("darkGrantsLevel",""), ("liveTestingDice",""), ("blackMarketTechDice",""), ("geneManipulationDice",""), ("neuralInterfaceDice",""), ("sleepDeprivationDice",""), ("overclockedEquipmentDice",""), ("childProdigyDice",""), ("assignedProdigyDice","")]:
            if fk in meta:
                fake_project[fk] = meta[fk]
        chars_by_name = {c.name: c for c in Character.objects.prefetch_related("character_merits__merit", "character_pulling_strings__pulling_string").all()}
        bases = list(agency.bases.all())
        computed = _compute_project_dice_pool(fake_project, agency, chars_by_name, bases)
        if computed:
            pool_size = max(computed["pool"], 1)

    # Check for auto-success merit activation
    auto_merit_name = None
    auto_successes = 0
    try:
        body = json.loads(request.body) if request.body else {}
        auto_merit_name = body.get("useAutoMerit")
    except (json.JSONDecodeError, AttributeError):
        pass

    if auto_merit_name and char:
        cm = char.character_merits.select_related("merit").filter(merit__name=auto_merit_name).first()
        if cm and cm.merit.effects.get("auto_success"):
            uses = char.merit_uses or {}
            used = uses.get(auto_merit_name, 0)
            if used < cm.rating:
                auto_successes = cm.rating
                uses[auto_merit_name] = used + 1
                char.merit_uses = uses
                char.save(update_fields=["merit_uses"])
            else:
                auto_merit_name = None
        else:
            auto_merit_name = None

    # Roll
    reroll_threshold = int(meta.get("rerollThreshold", 10) or 10)
    successes = 0
    rolls = []
    dice_left = pool_size
    while dice_left > 0:
        batch = []
        explosions = 0
        for _ in range(dice_left):
            die = random.randint(1, 10)
            batch.append(die)
            if die >= 8:
                successes += 1
            if die >= reroll_threshold:
                explosions += 1
        rolls.extend(batch)
        dice_left = explosions

    # Add auto-successes from merit
    successes += auto_successes

    # Add auto-successes from child prodigy (+2 per roll if assigned)
    prodigy_successes = 0
    if meta.get("assignedProdigyId"):
        prodigy_successes = 2
        successes += prodigy_successes

    old_score = afp.current_successes
    afp.current_successes = old_score + successes

    # Clear per-roll fringe effects from FTL metadata
    for per_roll_key in ["stimulantDice", "stimulants", "stimulantLocked", "stimulantResults",
                         "neuralInterface", "neuralInterfaceDice", "neuralInterfaceMlDamage", "neuralInterfaceAttrDamage",
                         "sleepDeprivation", "sleepDeprivationDice", "sleepDeprivationMlDamage"]:
        meta.pop(per_roll_key, None)
    afp.metadata = meta

    afp.save(update_fields=["current_successes", "metadata"])
    agency.project_rolls = rolls_data
    agency.save(update_fields=["project_rolls"])

    dice_successes = successes - auto_successes - prodigy_successes
    msg = roll_type.replace("_", " ").title() + " roll: " + str(pool_size) + " dice → " + str(dice_successes) + " successes."
    if auto_successes > 0:
        msg += " +" + str(auto_successes) + " auto (" + auto_merit_name + ")."
    if prodigy_successes > 0:
        msg += " +" + str(prodigy_successes) + " auto (Child Prodigy)."
    if auto_successes > 0 or prodigy_successes > 0:
        msg += " Total: " + str(successes) + " successes."
    if successes >= 5:
        msg += " EXCEPTIONAL SUCCESS!"
    if mental_damage:
        msg += " " + char_name + " takes 1 mental load."
    msg += " Progress: " + str(old_score) + " → " + str(afp.current_successes) + "/" + str(afp.ftl_project.required_successes) + "."

    # Log the roll
    try:
        ProjectRollLog.objects.create(
            agency=agency,
            assignment=afp,
            character_name=char_name,
            roll_type=roll_type,
            pool=pool_size,
            rolls=rolls,
            successes=successes,
            auto_successes=auto_successes + prodigy_successes,
            auto_merit=(auto_merit_name or "") + (" + Child Prodigy" if prodigy_successes > 0 else "") if (auto_successes > 0 or prodigy_successes > 0) else "",
            mental_damage=mental_damage,
            old_score=old_score,
            new_score=afp.current_successes,
            message=msg,
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Failed to log FTL roll")

    return JsonResponse({
        "rollType": roll_type, "pool": pool_size, "rolls": rolls,
        "successes": successes,
        "autoSuccesses": auto_successes + prodigy_successes,
        "autoMerit": (auto_merit_name or "") + (" + Child Prodigy" if prodigy_successes > 0 else "") if (auto_successes > 0 or prodigy_successes > 0) else None,
        "mentalDamage": mental_damage,
        "oldScore": old_score, "newScore": afp.current_successes, "message": msg,
    })


@login_required
@require_http_methods(["GET"])
def api_ftl_roll_log(request, pk, assignment_id):
    """Get roll log for an FTL project assignment."""
    afp = get_object_or_404(AgencyFTLProject, pk=assignment_id, agency_id=pk)
    logs = afp.roll_logs.all()[:50]
    data = [
        {
            "id": log.id,
            "characterName": log.character_name,
            "rollType": log.roll_type,
            "pool": log.pool,
            "rolls": log.rolls,
            "successes": log.successes,
            "autoSuccesses": log.auto_successes,
            "autoMerit": log.auto_merit or None,
            "mentalDamage": log.mental_damage,
            "oldScore": log.old_score,
            "newScore": log.new_score,
            "message": log.message,
            "rolledAt": log.rolled_at.isoformat(),
        }
        for log in logs
    ]
    return JsonResponse(data, safe=False)


@login_required
@require_http_methods(["POST"])
def api_downtime_action(request, pk):
    """Player spends a roll on a downtime action: rest, study, or assign NPC study."""
    agency = get_object_or_404(Agency, pk=pk)

    from characters.models import Character
    char = Character.objects.filter(owner=request.user).first()
    if not char and not request.user.is_superuser:
        return JsonResponse({"error": "No character found."}, status=400)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    action = body.get("action", "")
    if action not in ("rest", "study", "npc_study"):
        return JsonResponse({"error": "Invalid action."}, status=400)

    char_name = char.name if char else ""

    # Check and deduct roll
    rolls_data = agency.project_rolls or {}
    personal = rolls_data.get(char_name, {})
    total_free = personal.get("free", 0) or 0
    total_spare = personal.get("spare", 0) or 0

    if total_free <= 0 and total_spare <= 0:
        return JsonResponse({"error": "No rolls available."}, status=400)

    roll_type = "free" if total_free > 0 else "spare"
    if roll_type == "free":
        personal["free"] = total_free - 1
    else:
        personal["spare"] = total_spare - 1
    rolls_data[char_name] = personal

    messages = []

    # --- REST ---
    if action == "rest":
        if roll_type == "free":
            # Free rest: remove 2 mental load
            old_ml = char.mental_load or 0
            char.mental_load = max(0, old_ml - 2)
            char.save(update_fields=["mental_load"])
            messages.append(char_name + " rests. Mental load: " + str(old_ml) + " → " + str(char.mental_load) + " (-2).")
        else:
            # Spare time rest: remove 1 mental load (no extra ML tax)
            old_ml = char.mental_load or 0
            char.mental_load = max(0, old_ml - 1)
            char.save(update_fields=["mental_load"])
            messages.append(char_name + " rests in spare time. Mental load: " + str(old_ml) + " → " + str(char.mental_load) + " (-1).")

    # --- STUDY ---
    elif action == "study":
        if roll_type == "free":
            # Free study: +4 XP
            char.experience = (char.experience or 0) + 4
            char.save(update_fields=["experience"])
            messages.append(char_name + " studies. +4 XP.")
        else:
            # Spare time study: +2 XP, +1 mental load
            char.experience = (char.experience or 0) + 2
            char.mental_load = (char.mental_load or 0) + 1
            char.save(update_fields=["experience", "mental_load"])
            messages.append(char_name + " studies in spare time. +2 XP, +1 mental load.")

    # --- NPC STUDY ---
    elif action == "npc_study":
        npc_id = body.get("npcId")
        if not npc_id:
            return JsonResponse({"error": "Select an NPC."}, status=400)
        from npcs.models import NPC
        npc = NPC.objects.filter(id=npc_id).first()
        if not npc:
            return JsonResponse({"error": "NPC not found."}, status=400)

        # Both free and spare: +5 XP to NPC
        npc.experience = (npc.experience or 0) + 5
        npc.save(update_fields=["experience"])
        messages.append(npc.name + " studies. +5 XP.")

        if roll_type == "spare":
            # Spare time: +1 mental load to player
            char.mental_load = (char.mental_load or 0) + 1
            char.save(update_fields=["mental_load"])
            messages.append(char_name + " takes 1 mental load (spare time supervision).")

    agency.project_rolls = rolls_data
    agency.save(update_fields=["project_rolls"])

    return JsonResponse({
        "action": action,
        "rollType": roll_type,
        "messages": messages,
        "message": "\n".join(messages),
    })


# ---------------------------------------------------------------------------
# Phase 1/2 — Per-section PATCH endpoints with optimistic concurrency.
#
# The legacy PUT /api/agencies/<pk>/bases/<base_id>/ endpoint silently dropped
# concurrent writes via an ``existing.issubset(proposed)`` check (two players
# adding different items to the same base would lose one write). The endpoints
# below replace that with explicit version negotiation:
#
#   * Each agency section tracks a monotonic version in agency.section_versions
#     (a JSON map). Per-base sections track their version on Base.version.
#   * Clients send the expected current version in the If-Match header.
#   * On mismatch the server returns 409 with {current_version, current_value}
#     so the client can rebase and retry.
#   * Missing If-Match is treated as a force-write (still bumps version),
#     mainly so MCP / automation tooling doesn't have to track versions.
# ---------------------------------------------------------------------------


def _admin_only(request, agency):
    """Return a 403 JsonResponse for non-admins, else None."""
    if not request.user.is_superuser:
        return JsonResponse(
            {"error": "ACCESS DENIED. Administrator clearance required."},
            status=403,
        )
    return None


def _user_belongs_to_player_agency(user, agency):
    """True iff ``user`` owns a character assigned to a workspace on a base
    of ``agency`` (and ``agency`` is the player agency).

    Mirrors the membership rule used on the council page (see council_page).
    Superusers are always considered members.
    """
    if user.is_superuser:
        return True
    if not agency.is_player_agency:
        return False
    char_ids = set(user.characters.values_list("id", flat=True))
    if not char_ids:
        return False
    for base in agency.bases.all():
        for ws in base.workspaces or []:
            if (
                ws.get("assignedType") == "character"
                and ws.get("assignedTo") in char_ids
            ):
                return True
    return False


def _admin_or_player_member(request, agency):
    """Permission check for sections any player on the agency can edit
    (e.g. the shared notes pad). Returns 403 JsonResponse or None.
    """
    if request.user.is_superuser:
        return None
    if _user_belongs_to_player_agency(request.user, agency):
        return None
    return JsonResponse(
        {"error": "ACCESS DENIED. You are not a member of this agency."},
        status=403,
    )


def _parse_if_match(request):
    """Parse the If-Match header. Returns (expected_version, error_response).

    On a missing header, returns (None, None) — the caller treats this as a
    force-write. On a malformed header, returns (None, JsonResponse(400)).
    """
    raw = request.headers.get("If-Match")
    if raw is None or raw == "":
        return None, None
    # Strip optional weak/strong ETag wrapping characters.
    stripped = raw.strip().strip('"').strip("W/").strip('"')
    try:
        return int(stripped), None
    except ValueError:
        return None, JsonResponse({"error": "Invalid If-Match header"}, status=400)


def _conflict_response(section_key, current_version, current_value):
    """Build the 409 response shape described in the API contract."""
    return JsonResponse(
        {
            "error": "Stale write — section was updated by another user.",
            "current_version": int(current_version or 0),
            "current_value": current_value,
        },
        status=409,
    )


def _ok_response(payload, version):
    """Build the 200 response with ETag set to the new version."""
    response = JsonResponse(payload)
    response["ETag"] = str(version)
    return response


def _agency_section_patch(
    request,
    pk,
    section_key,
    perm_check,
    write_fn,
    *,
    extra_update_fields=(),
):
    """Core handler for agency-level section PATCH.

    Uses a compare-and-swap UPDATE so the version check is atomic at the SQL
    level. This works on every backend (including SQLite, where
    ``select_for_update()`` is silently dropped and a Python-side check has
    a TOCTOU race window).

    Strategy:
        1. Read the agency, run perm + visibility checks against it.
        2. Call ``write_fn(agency, data)`` to mutate ``agency`` in memory and
           validate. ``write_fn`` MUST NOT call ``.save()``.
        3. Build the new ``section_versions`` dict (bump only our key) and
           emit a single ``UPDATE`` whose ``WHERE`` clause pins the row to
           the *previous* ``section_versions`` value. The row count from
           ``.update()`` is the CAS primitive: ``1`` = won, ``0`` = lost.

    Trade-off (JSON-dict-CAS): the WHERE clause pins the *whole* JSON dict,
    not just our key. So a concurrent write to a *different* section in the
    same window will also fail our CAS with 409. That's stricter than the
    contract requires, but it's correct (never silent-drops a write) and the
    spurious-409 case is rare and recoverable (the client re-fetches and
    retries). A migration to per-section columns would tighten this; deferred.

    Args:
        perm_check: ``callable(request, agency) -> Optional[JsonResponse]``.
            Returning a response short-circuits with that response.
        write_fn: ``callable(agency, payload_dict) -> Optional[JsonResponse]``.
            Mutates ``agency`` in memory based on ``payload_dict``. Returning
            a response (e.g. validation error) short-circuits. MUST NOT save.
        extra_update_fields: extra concrete fields touched by ``write_fn``
            (mapped to the columns in the atomic UPDATE).
    """
    try:
        data = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid data stream."}, status=400)

    expected, err = _parse_if_match(request)
    if err is not None:
        return err

    try:
        agency = Agency.objects.get(pk=pk)
    except Agency.DoesNotExist:
        return JsonResponse({"error": "Agency record not found."}, status=404)

    if agency.is_hidden and not request.user.is_superuser:
        return JsonResponse(
            {"error": "ACCESS DENIED. Agency record not found."}, status=404
        )

    perm_resp = perm_check(request, agency)
    if perm_resp is not None:
        return perm_resp

    # Force-write path retries the CAS on conflict (last-writer-wins
    # semantics). For If-Match writes a single CAS attempt is correct —
    # a CAS miss means a real concurrency conflict that the client must see.
    max_attempts = 1 if expected is not None else 5

    for attempt in range(max_attempts):
        # Wrap each CAS attempt in an atomic block. This gives us a clean
        # BEGIN/COMMIT boundary so SQLite serialises concurrent writers via
        # its file lock (without atomic(), concurrent writers can race on
        # sqlite3 connection state under the in-memory shared-cache test
        # backend). The CAS itself remains the source of truth.
        with transaction.atomic():
            # Re-read inside the transaction so retries — and our
            # CAS-snapshot — observe any concurrent commits.
            agency.refresh_from_db()
            pre_versions = dict(agency.section_versions or {})
            current = int(pre_versions.get(section_key, 0))

            if expected is not None and expected != current:
                current_value = serialize_agency_section(
                    agency, section_key, request.user
                )[section_key]
                return _conflict_response(section_key, current, current_value)

            # Mutate ``agency`` in memory (write_fn must not call .save()).
            write_resp = write_fn(agency, data)
            if write_resp is not None:
                return write_resp

            new_version = current + 1
            new_versions = dict(pre_versions)
            new_versions[section_key] = new_version

            # Build the kwargs for the UPDATE — only the columns the writer
            # touched plus our version bump and updated_at. Reading them off
            # the in-memory ``agency`` reflects whatever write_fn just set.
            update_kwargs = {
                field: getattr(agency, field) for field in extra_update_fields
            }
            update_kwargs["section_versions"] = new_versions
            update_kwargs["updated_at"] = timezone.now()

            # Atomic compare-and-swap. The WHERE pin makes the version
            # check happen at SQL level — no TOCTOU window even on SQLite.
            updated = Agency.objects.filter(
                pk=agency.pk,
                section_versions=pre_versions,
            ).update(**update_kwargs)

            if updated:
                # Refresh once so the response reflects DB-canonical state
                # (handles e.g. JSON normalisation by the backend).
                agency.refresh_from_db()
                payload = serialize_agency_section(
                    agency, section_key, request.user
                )
                return _ok_response(payload, new_version)

        # CAS miss. For force-writes, retry on the next loop iteration.
        # For If-Match writes the loop ends and we 409 below.
        agency.refresh_from_db()

    # Lost the race (If-Match path, or force-write exhausted all retries).
    # Return canonical state in a 409 so the client can rebase and retry.
    live_versions = agency.section_versions or {}
    live_current = int(live_versions.get(section_key, 0))
    current_value = serialize_agency_section(
        agency, section_key, request.user
    )[section_key]
    return _conflict_response(section_key, live_current, current_value)


def _base_section_patch(
    request,
    pk,
    base_id,
    section_key,
    write_fn,
    *,
    extra_update_fields=(),
):
    """Core handler for per-base section PATCH.

    Uses a compare-and-swap UPDATE on ``Base.version`` so the concurrency
    check is atomic at the SQL level. Works on every backend (SQLite drops
    ``select_for_update()``, so a Python-side check has a TOCTOU race; the
    CAS-via-WHERE-clause pattern closes that window).

    Strategy:
        1. Read the base + its agency. Run permission and visibility checks.
        2. Call ``write_fn(request, agency, base, data)`` to mutate ``base``
           in memory and run any cross-field validation. ``write_fn`` MUST
           NOT call ``.save()``.
        3. Emit a single ``UPDATE`` whose ``WHERE`` clause pins ``version``
           to the previously-read value. The row count is the CAS primitive.

    Force-writes (no If-Match) retry the CAS on miss for last-writer-wins
    semantics; If-Match writes attempt once and then 409.
    """
    try:
        data = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid data stream."}, status=400)

    expected, err = _parse_if_match(request)
    if err is not None:
        return err

    try:
        agency = Agency.objects.get(pk=pk)
    except Agency.DoesNotExist:
        return JsonResponse({"error": "Agency record not found."}, status=404)

    if agency.is_hidden and not request.user.is_superuser:
        return JsonResponse(
            {"error": "ACCESS DENIED. Agency record not found."}, status=404
        )

    try:
        base = Base.objects.get(pk=base_id, agency_id=pk)
    except Base.DoesNotExist:
        return JsonResponse({"error": "Base record not found."}, status=404)

    if base.is_hidden and not request.user.is_superuser:
        return JsonResponse(
            {"error": "ACCESS DENIED. Base record not found."}, status=404
        )

    # Force-writes retry the CAS on miss. If-Match writes attempt once then
    # 409 — a CAS miss with a client-supplied expectation IS the conflict.
    max_attempts = 1 if expected is not None else 5

    for attempt in range(max_attempts):
        # Wrap each CAS attempt in an atomic block. This gives us a clean
        # BEGIN/COMMIT boundary so SQLite serialises concurrent writers via
        # its file lock (without atomic(), each ORM call is its own
        # autocommit transaction and concurrent writers can hit
        # ``sqlite3.InterfaceError`` under the in-memory shared-cache test
        # backend). The CAS itself remains the source of truth — atomic()
        # just keeps the session/connection state sane around it.
        with transaction.atomic():
            # Re-read the base inside the transaction so we observe any
            # commits from a concurrent writer that finished between our
            # outer .get() and now.
            base.refresh_from_db()
            current = int(base.version or 0)
            if expected is not None and expected != current:
                current_value = serialize_base_section(
                    base, section_key
                )[section_key]
                return _conflict_response(section_key, current, current_value)

            # Mutate ``base`` in memory (write_fn must not call .save()).
            write_resp = write_fn(request, agency, base, data)
            if write_resp is not None:
                return write_resp

            new_version = current + 1

            # Pull the writer's mutations off the in-memory ``base`` for the
            # atomic UPDATE.
            update_kwargs = {
                field: getattr(base, field) for field in extra_update_fields
            }
            update_kwargs["version"] = new_version
            update_kwargs["updated_at"] = timezone.now()

            # Atomic compare-and-swap on Base.version. The WHERE pin closes
            # the TOCTOU window that select_for_update() leaves open on
            # SQLite.
            updated = Base.objects.filter(
                pk=base.pk,
                version=current,
            ).update(**update_kwargs)

            if updated:
                base.refresh_from_db()
                payload = serialize_base_section(base, section_key)
                return _ok_response(payload, new_version)

        # CAS miss. Loop iterates: force-writes retry; If-Match writes drop
        # out below for a 409.
        base.refresh_from_db()

    # If-Match write lost the race, or force-write exhausted retries.
    live_current = int(base.version or 0)
    current_value = serialize_base_section(base, section_key)[section_key]
    return _conflict_response(section_key, live_current, current_value)


# ---------------------------------------------------------------------------
# Agency-level section write functions.
# Each takes (agency, data) and mutates ``agency`` in place. Returning a
# JsonResponse short-circuits the patch (used for validation errors).
# ---------------------------------------------------------------------------


def _write_header(agency, data):
    if "name" in data:
        agency.name = data["name"] or ""
    if "motto" in data:
        agency.motto = data["motto"] or ""
    if "headquarters" in data:
        agency.headquarters = data["headquarters"] or ""
    return None


def _write_alliance(agency, data):
    if "alliance" in data:
        agency.alliance = data["alliance"]
    return None


def _write_notes(agency, data):
    if "notes" in data:
        agency.notes = data["notes"] or ""
    return None


def _write_integrity(agency, data):
    if "integrity" in data:
        try:
            agency.integrity = int(data["integrity"])
        except (TypeError, ValueError):
            return JsonResponse({"error": "integrity must be an integer."}, status=400)
    return None


def _write_attributes(agency, data):
    if "attributes" in data:
        agency.attributes = data["attributes"]
    return None


def _write_specializations(agency, data):
    if "specializations" in data:
        agency.specializations = data["specializations"] or []
    return None


def _write_merits(agency, data):
    if "merits" in data:
        agency.merits = data["merits"] or []
    return None


def _write_flaws(agency, data):
    if "flaws" in data:
        agency.flaws = data["flaws"] or []
    return None


def _write_assets(agency, data):
    if "assets" in data:
        agency.assets = data["assets"] or []
    return None


def _write_fleet(agency, data):
    if "fleet" in data:
        agency.fleet = data["fleet"] or []
    return None


def _write_history(agency, data):
    if "history" in data:
        agency.history = data["history"] or []
    return None


def _write_admin_flags(agency, data):
    """Combined endpoint for the small admin toggles. We accept any subset
    of the supported keys so the frontend can patch one switch at a time
    without touching the others.
    """
    if "mapColor" in data:
        agency.map_color = data["mapColor"] or ""
    if "isNuclearPower" in data:
        agency.is_nuclear_power = bool(data["isNuclearPower"])
    if "isHidden" in data:
        agency.is_hidden = bool(data["isHidden"])
    if "sweepPool" in data:
        try:
            agency.sweep_pool = int(data["sweepPool"])
        except (TypeError, ValueError):
            return JsonResponse({"error": "sweepPool must be an integer."}, status=400)
    if "zeroDayPool" in data:
        try:
            agency.zero_day_pool = int(data["zeroDayPool"])
        except (TypeError, ValueError):
            return JsonResponse({"error": "zeroDayPool must be an integer."}, status=400)
    return None


# Map a section_key to (write_fn, perm_check, model_fields).
# ``model_fields`` is the concrete column(s) the writer touches; passed to
# Django's ``update_fields`` so we don't clobber unrelated state on save.
_AGENCY_SECTION_HANDLERS = {
    "header": (
        _write_header,
        _admin_only,
        ("name", "motto", "headquarters"),
    ),
    "alliance": (_write_alliance, _admin_only, ("alliance",)),
    "notes": (_write_notes, _admin_or_player_member, ("notes",)),
    "integrity": (_write_integrity, _admin_only, ("integrity",)),
    "attributes": (_write_attributes, _admin_only, ("attributes",)),
    "specializations": (_write_specializations, _admin_only, ("specializations",)),
    "merits": (_write_merits, _admin_only, ("merits",)),
    "flaws": (_write_flaws, _admin_only, ("flaws",)),
    "assets": (_write_assets, _admin_only, ("assets",)),
    "fleet": (_write_fleet, _admin_only, ("fleet",)),
    "history": (_write_history, _admin_only, ("history",)),
    "admin-flags": (
        _write_admin_flags,
        _admin_only,
        ("map_color", "is_nuclear_power", "is_hidden", "sweep_pool", "zero_day_pool"),
    ),
}


def _agency_section_view(section_key):
    """Build a thin view wrapper for an agency section.

    Returns a Django view ``f(request, pk)`` that dispatches to
    ``_agency_section_patch`` with the right write/perm callables. Used to
    instantiate the 12 named URL targets without 12 copies of the boilerplate.
    """
    write_fn, perm_check, fields = _AGENCY_SECTION_HANDLERS[section_key]

    @login_required
    @require_http_methods(["PATCH"])
    def view(request, pk):
        return _agency_section_patch(
            request,
            pk,
            section_key,
            perm_check,
            write_fn,
            extra_update_fields=fields,
        )

    view.__name__ = f"api_agency_section_{section_key.replace('-', '_')}"
    return view


api_agency_section_header = _agency_section_view("header")
api_agency_section_alliance = _agency_section_view("alliance")
api_agency_section_notes = _agency_section_view("notes")
api_agency_section_integrity = _agency_section_view("integrity")
api_agency_section_attributes = _agency_section_view("attributes")
api_agency_section_specializations = _agency_section_view("specializations")
api_agency_section_merits = _agency_section_view("merits")
api_agency_section_flaws = _agency_section_view("flaws")
api_agency_section_assets = _agency_section_view("assets")
api_agency_section_fleet = _agency_section_view("fleet")
api_agency_section_history = _agency_section_view("history")
api_agency_section_admin_flags = _agency_section_view("admin-flags")


# ---------------------------------------------------------------------------
# Per-base section write functions.
#
# Player permission: additive-only. If proposed removes any items from
# existing, return 403 (replaces the legacy silent issubset drop). Admins
# can do anything.
# ---------------------------------------------------------------------------


def _player_additive_violation(existing_set, proposed_set, label):
    """Return a 403 JsonResponse if a player is trying to remove items.

    ``label`` is used in the error message ("merits", "facilities", ...).
    """
    removed = existing_set - proposed_set
    if removed:
        return JsonResponse(
            {
                "error": (
                    f"ACCESS DENIED. Players can only add {label}; "
                    f"removing requires administrator clearance."
                )
            },
            status=403,
        )
    return None


def _validate_player_xp_and_space(agency, base):
    """Re-check the XP budget and space cap after a player edit.

    Mirrors the legacy validation in api_agency_base_detail so we don't lose
    that protection when shifting players to the per-section endpoints.
    """
    config = BaseConfig.load()
    lt_by_key = {lt["key"]: lt for lt in (config.location_types or [])}
    merit_by_key = {m["key"]: m for m in (config.location_merits or [])}
    ft_by_key = {ft["key"]: ft for ft in (config.facility_types or [])}
    eq_by_key = {eq["key"]: eq for eq in (config.equipment_types or [])}

    def calc(b_loc, b_merits, b_facilities, b_workspaces, b_equipment):
        total_exp = 0
        total_space = 0
        used_space = 0
        lt = lt_by_key.get(b_loc)
        if lt:
            total_exp += lt.get("exp", 0)
            total_space += lt.get("space", 0)
        for mk in (b_merits or []):
            m = merit_by_key.get(mk)
            if m:
                total_exp += m.get("exp", 0)
                total_space += m.get("extraSpace", 0)
        for f in (b_facilities or []):
            ft = ft_by_key.get(f.get("key"))
            if ft:
                lvl = next(
                    (l for l in ft.get("levels", []) if l["level"] == f.get("level")),
                    None,
                )
                if lvl:
                    total_exp += lvl.get("exp", 0)
                    used_space += lvl.get("size", 0)
        ws_ft = ft_by_key.get("workspace")
        for w in (b_workspaces or []):
            if ws_ft:
                lvl = next(
                    (l for l in ws_ft.get("levels", []) if l["level"] == w.get("level")),
                    None,
                )
                if lvl:
                    total_exp += lvl.get("exp", 0)
                    used_space += lvl.get("size", 0)
        for ek in (b_equipment or []):
            eq = eq_by_key.get(ek)
            if eq:
                total_exp += eq.get("exp", 0)
        return total_exp, total_space, used_space

    new_exp, new_total_space, new_used_space = calc(
        base.location_type, base.merits, base.facilities, base.workspaces, base.equipment
    )

    other_bases_exp = sum(
        calc(b.location_type, b.merits, b.facilities, b.workspaces, b.equipment)[0]
        for b in agency.bases.exclude(pk=base.pk)
    )
    if other_bases_exp + new_exp > (agency.experience or 0):
        return JsonResponse(
            {
                "error": (
                    "Not enough agency XP. Need "
                    + str(other_bases_exp + new_exp)
                    + " but agency has "
                    + str(agency.experience or 0)
                    + "."
                )
            },
            status=400,
        )

    if new_used_space > new_total_space and new_total_space > 0:
        return JsonResponse(
            {
                "error": (
                    "Not enough space. Used "
                    + str(new_used_space)
                    + " of "
                    + str(new_total_space)
                    + " available."
                )
            },
            status=400,
        )
    return None


def _write_base_name(request, agency, base, data):
    if "name" not in data:
        return None
    if not request.user.is_superuser:
        return JsonResponse({"error": "ACCESS DENIED."}, status=403)
    base.name = data["name"] or ""
    return None


def _write_base_location(request, agency, base, data):
    """Field name aliases: payload may use ``location`` or ``locationType``."""
    if "location" not in data and "locationType" not in data:
        return None
    new_loc = data.get("location", data.get("locationType")) or ""
    if request.user.is_superuser:
        base.location_type = new_loc
        return None
    # Player rule: location can be set if currently empty, never changed.
    if base.location_type and base.location_type != new_loc:
        return JsonResponse(
            {"error": "ACCESS DENIED. Location may only be set once."}, status=403
        )
    if not base.location_type and new_loc:
        base.location_type = new_loc
    return _validate_player_xp_and_space(agency, base) if base.location_type else None


def _write_base_merits(request, agency, base, data):
    if "merits" not in data:
        return None
    proposed = data["merits"] or []
    if request.user.is_superuser:
        base.merits = proposed
        return None
    existing_set = set(base.merits or [])
    proposed_set = set(proposed)
    violation = _player_additive_violation(existing_set, proposed_set, "merits")
    if violation is not None:
        return violation
    base.merits = proposed
    return _validate_player_xp_and_space(agency, base)


def _write_base_facilities(request, agency, base, data):
    if "facilities" not in data:
        return None
    proposed = data["facilities"] or []
    if request.user.is_superuser:
        base.facilities = proposed
        return None
    # Compare by (key, level) tuples — a level upgrade is a different item.
    existing_set = {(f.get("key"), f.get("level")) for f in (base.facilities or [])}
    proposed_set = {(f.get("key"), f.get("level")) for f in proposed}
    violation = _player_additive_violation(existing_set, proposed_set, "facilities")
    if violation is not None:
        return violation
    base.facilities = proposed
    return _validate_player_xp_and_space(agency, base)


def _write_base_workspaces(request, agency, base, data):
    if "workspaces" not in data:
        return None
    proposed = data["workspaces"] or []
    if request.user.is_superuser:
        base.workspaces = proposed
        return None
    # Workspaces don't have a stable key — replicate the legacy "list cannot
    # shrink" rule from api_agency_base_detail.
    if len(proposed) < len(base.workspaces or []):
        return JsonResponse(
            {
                "error": (
                    "ACCESS DENIED. Players can only add workspaces; "
                    "removing requires administrator clearance."
                )
            },
            status=403,
        )
    base.workspaces = proposed
    return _validate_player_xp_and_space(agency, base)


def _write_base_equipment(request, agency, base, data):
    if "equipment" not in data:
        return None
    proposed = data["equipment"] or []
    if request.user.is_superuser:
        base.equipment = proposed
        return None
    existing_set = set(base.equipment or [])
    proposed_set = set(proposed)
    violation = _player_additive_violation(existing_set, proposed_set, "equipment")
    if violation is not None:
        return violation
    base.equipment = proposed
    return _validate_player_xp_and_space(agency, base)


def _write_base_departments(request, agency, base, data):
    if "departments" not in data:
        return None
    base.departments = data["departments"] or []
    return None


def _write_base_notes(request, agency, base, data):
    if "notes" not in data:
        return None
    # Players belonging to the agency can edit notes on a player-agency base.
    if not request.user.is_superuser and not _user_belongs_to_player_agency(
        request.user, agency
    ):
        return JsonResponse({"error": "ACCESS DENIED."}, status=403)
    base.notes = data["notes"] or ""
    return None


def _write_base_geo(request, agency, base, data):
    if not request.user.is_superuser:
        return JsonResponse({"error": "ACCESS DENIED."}, status=403)
    if "latitude" in data:
        base.latitude = data["latitude"] if data["latitude"] is not None else None
    if "longitude" in data:
        base.longitude = data["longitude"] if data["longitude"] is not None else None
    return None


def _write_base_hidden(request, agency, base, data):
    if not request.user.is_superuser:
        return JsonResponse({"error": "ACCESS DENIED."}, status=403)
    if "hidden" in data:
        base.is_hidden = bool(data["hidden"])
    elif "isHidden" in data:
        base.is_hidden = bool(data["isHidden"])
    return None


def _write_base_classified(request, agency, base, data):
    """Manage which sections of the base are redacted from non-admins
    (the existing ``hidden_sections`` JSON list on Base).
    """
    if not request.user.is_superuser:
        return JsonResponse({"error": "ACCESS DENIED."}, status=403)
    if "classified" in data:
        base.hidden_sections = data["classified"] or []
    elif "hiddenSections" in data:
        base.hidden_sections = data["hiddenSections"] or []
    return None


_BASE_SECTION_HANDLERS = {
    "name": (_write_base_name, ("name",)),
    "location": (_write_base_location, ("location_type",)),
    "merits": (_write_base_merits, ("merits",)),
    "facilities": (_write_base_facilities, ("facilities",)),
    "workspaces": (_write_base_workspaces, ("workspaces",)),
    "equipment": (_write_base_equipment, ("equipment",)),
    "departments": (_write_base_departments, ("departments",)),
    "notes": (_write_base_notes, ("notes",)),
    "geo": (_write_base_geo, ("latitude", "longitude")),
    "hidden": (_write_base_hidden, ("is_hidden",)),
    "classified": (_write_base_classified, ("hidden_sections",)),
}


@login_required
@require_http_methods(["PATCH"])
def api_agency_base_section(request, pk, base_id, section_key):
    """Per-base section PATCH endpoint.

    URL: ``PATCH /api/agencies/<pk>/bases/<base_id>/section/<section_key>/``

    See the file-level header for the optimistic-concurrency contract. The
    section_key must be one of the keys in ``_BASE_SECTION_HANDLERS``.
    """
    handler = _BASE_SECTION_HANDLERS.get(section_key)
    if handler is None:
        return JsonResponse(
            {"error": f"Unknown section key: {section_key!r}"}, status=404
        )
    write_fn, fields = handler
    return _base_section_patch(
        request,
        pk,
        base_id,
        section_key,
        write_fn,
        extra_update_fields=fields,
    )
