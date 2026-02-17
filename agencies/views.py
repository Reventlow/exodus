import json

from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from .models import Agency, ChangeRequest
from .serializers import (
    serialize_agency,
    serialize_agency_summary,
    serialize_change_request,
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

        # Update boolean
        if "isPlayerAgency" in data:
            agency.is_player_agency = data["isPlayerAgency"]

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
