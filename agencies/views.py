import json
from pathlib import Path

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from .models import Agency, ChangeRequest, GlobalFlaw, FTLProject, AgencyFTLProject, CouncilItem
from .serializers import (
    serialize_agency,
    serialize_agency_summary,
    serialize_change_request,
    serialize_global_flaw,
    serialize_ftl_project,
    serialize_agency_ftl_project,
    serialize_council_item,
)


# ---------------------------------------------------------------------------
# Page views (return HTML)
# ---------------------------------------------------------------------------


@login_required
def agency_list_page(request):
    """Dashboard showing all agencies."""
    return render(request, "agencies/list.html")


@login_required
def agency_sheet_page(request, pk):
    """Agency sheet page. Shows full agency with React frontend."""
    agency = get_object_or_404(Agency, pk=pk)
    is_admin = request.user.is_superuser
    return render(
        request,
        "agencies/sheet.html",
        {
            "agency_id": agency.id,
            "is_admin": is_admin,
            "is_player_agency": agency.is_player_agency,
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
    return render(request, "agencies/council.html")


@login_required
def council_charter_page(request):
    """UIC Charter page. Readable by all logged-in users."""
    charter_path = Path(settings.BASE_DIR) / "UIC_CHARTER.md"
    charter_content = charter_path.read_text() if charter_path.exists() else ""
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

    # POST — admin only
    if not request.user.is_superuser:
        return JsonResponse(
            {"error": "ACCESS DENIED. Administrator clearance required."}, status=403
        )
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        body = {}

    ci = CouncilItem.objects.create(
        name=body.get("name", "NEW COUNCIL ITEM"),
        item_type=body.get("itemType", "agreement"),
        description=body.get("description", ""),
        status=body.get("status", "proposed"),
        proposed_by=body.get("proposedBy", ""),
        notes=body.get("notes", ""),
        order=body.get("order", 0),
    )
    return JsonResponse(serialize_council_item(ci), status=201)


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
def api_council_detail(request, pk):
    """GET/PUT/DELETE a single council item. Admin only."""
    if not request.user.is_superuser:
        return JsonResponse(
            {"error": "ACCESS DENIED. Administrator clearance required."}, status=403
        )

    ci = get_object_or_404(CouncilItem, pk=pk)

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
        return JsonResponse(serialize_council_item(ci))

    if request.method == "DELETE":
        ci.delete()
        return JsonResponse({"status": "Council item record terminated."})


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
