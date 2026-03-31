import json
from pathlib import Path

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from .models import Agency, ChangeRequest, GlobalFlaw, FTLProject, AgencyFTLProject, CouncilItem, CouncilVote, BaseConfig, Base
from .serializers import (
    serialize_agency,
    serialize_agency_summary,
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


def _broadcast_council_item(ci):
    """Broadcast an updated council item to all WebSocket clients."""
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        COUNCIL_GROUP,
        {
            "type": "council_update",
            "item": serialize_council_item(ci),
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
            agency.projects = data["projects"]
        if "history" in data:
            agency.history = data["history"]
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
        afp.current_successes = data["currentSuccesses"]
        afp.save(update_fields=["current_successes"])

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
        data = [serialize_council_item(ci) for ci in items]
        return JsonResponse(data, safe=False)

    # POST — admin or any logged-in user with an agency
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
    return JsonResponse(serialize_council_item(ci), status=201)


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
def api_council_detail(request, pk):
    """GET/PUT/DELETE a single council item."""
    ci = get_object_or_404(CouncilItem, pk=pk)

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
                    return JsonResponse(serialize_council_item(ci))
                # voting → emergency_suspended
                if ci.status == "voting" and new_status == "emergency_suspended":
                    ci.vote_record = build_vote_record(ci)
                    ci.status = "emergency_suspended"
                    ci.save()
                    _broadcast_council_item(ci)
                    return JsonResponse(serialize_council_item(ci))

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
                return JsonResponse(serialize_council_item(ci))

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
        return JsonResponse(serialize_council_item(ci))

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

        ci.save()
        _broadcast_council_item(ci)
        return JsonResponse(serialize_council_item(ci))

    if request.method == "DELETE":
        ci.delete()
        return JsonResponse({"status": "Council item record terminated."})


@login_required
@require_http_methods(["PUT"])
def api_council_reorder(request):
    """Bulk reorder council items. Admin or chairman agency player."""
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
        [serialize_council_item(ci) for ci in all_items], safe=False
    )


@login_required
@require_http_methods(["POST"])
def api_council_vote(request, pk):
    """Cast or update a vote on a council item. Body: {agencyId, vote}.

    Admin can vote for any council member agency.
    Players can only vote for their own agency.
    Item must be in 'voting' status.
    """
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
    return JsonResponse(serialize_council_item(ci))


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
    """Toggle an agency's council presence. Chairman or admin only."""
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
    """GET/PUT/DELETE a single base. Admin only for PUT/DELETE."""
    base = get_object_or_404(Base, pk=base_id, agency_id=pk)

    if request.method == "GET":
        if base.is_hidden and not request.user.is_superuser:
            return JsonResponse(
                {"error": "ACCESS DENIED. Base record not found."}, status=404
            )
        return JsonResponse(serialize_base(base, is_admin=request.user.is_superuser))

    if not request.user.is_superuser:
        return JsonResponse(
            {"error": "ACCESS DENIED. Administrator clearance required."}, status=403
        )

    if request.method == "DELETE":
        base.delete()
        return JsonResponse({"status": "Base record terminated."})

    # PUT
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid data stream."}, status=400)

    if "name" in data:
        base.name = data["name"]
    if "locationType" in data:
        base.location_type = data["locationType"]
    if "merits" in data:
        base.merits = data["merits"]
    if "facilities" in data:
        base.facilities = data["facilities"]
    if "workspaces" in data:
        base.workspaces = data["workspaces"]
    if "equipment" in data:
        base.equipment = data["equipment"]
    if "notes" in data:
        base.notes = data["notes"]
    if "isHidden" in data:
        base.is_hidden = bool(data["isHidden"])
    if "hiddenSections" in data:
        base.hidden_sections = data["hiddenSections"]
    if "latitude" in data:
        base.latitude = data["latitude"] if data["latitude"] is not None else None
    if "longitude" in data:
        base.longitude = data["longitude"] if data["longitude"] is not None else None

    base.save()
    return JsonResponse(serialize_base(base))


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

    for i in range(level):
        die = random.randint(1, 10)
        rolls.append(die)
        if die <= 3 and npc_agencies:
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
