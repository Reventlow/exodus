import json
import os

from django.contrib.auth.models import User
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods

from .models import NPC
from .serializers import serialize_npc, serialize_npc_summary


# ---------------------------------------------------------------------------
# Page views (return HTML)
# ---------------------------------------------------------------------------

@login_required
def npc_list_page(request):
    """NPC dossier list page."""
    return render(request, "npcs/list.html")


@login_required
def npc_detail_page(request, pk):
    """NPC detail page. Editable for assigned user or admin."""
    npc = get_object_or_404(NPC, pk=pk)
    is_editor = request.user == npc.assigned_to or request.user.is_superuser
    is_admin = request.user.is_superuser
    return render(request, "npcs/detail.html", {
        "npc_id": npc.id,
        "is_editor": is_editor,
        "is_admin": is_admin,
    })


# ---------------------------------------------------------------------------
# API views (return JSON)
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["GET", "POST"])
def api_npc_list(request):
    """GET: list all NPCs. POST: create a new NPC."""
    if request.method == "GET":
        npcs = NPC.objects.select_related("assigned_to").all()
        data = [serialize_npc_summary(n) for n in npcs]
        return JsonResponse(data, safe=False)

    # POST - create new NPC
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        body = {}

    npc = NPC.objects.create(
        name=body.get("name", "UNKNOWN CONTACT"),
        assigned_to=request.user,
        created_by=request.user,
    )
    return JsonResponse(serialize_npc(npc), status=201)


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
def api_npc_detail(request, pk):
    """GET: full NPC data. PUT: update (assigned_to or admin). DELETE: admin only."""
    npc = get_object_or_404(NPC, pk=pk)

    if request.method == "GET":
        return JsonResponse(serialize_npc(npc))

    if request.method == "PUT":
        # Only assigned user or admin can update
        if request.user != npc.assigned_to and not request.user.is_superuser:
            return JsonResponse({"error": "ACCESS DENIED."}, status=403)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid data stream."}, status=400)

        # Update text fields
        for field in ("name", "sex", "pronouns", "nationality", "occupation", "bio"):
            if field in data:
                setattr(npc, field, data[field])

        # Update age (nullable integer)
        if "age" in data:
            npc.age = data["age"] if data["age"] else None

        # Update state
        if "state" in data:
            valid_states = [s[0] for s in NPC.STATE_CHOICES]
            if data["state"] in valid_states:
                npc.state = data["state"]

        # Admin can reassign
        if "assignedToId" in data and request.user.is_superuser:
            try:
                new_user = User.objects.get(pk=data["assignedToId"])
                npc.assigned_to = new_user
            except User.DoesNotExist:
                pass

        npc.save()
        return JsonResponse(serialize_npc(npc))

    if request.method == "DELETE":
        if not request.user.is_superuser:
            return JsonResponse(
                {"error": "ACCESS DENIED. Administrator clearance required."},
                status=403,
            )
        npc.delete()
        return JsonResponse({"status": "Record terminated."})


@login_required
@require_http_methods(["POST"])
def api_npc_image(request, pk):
    """Upload NPC portrait image."""
    npc = get_object_or_404(NPC, pk=pk)

    # Only assigned user or admin can upload
    if request.user != npc.assigned_to and not request.user.is_superuser:
        return JsonResponse({"error": "ACCESS DENIED."}, status=403)

    image = request.FILES.get("image")
    if not image:
        return JsonResponse({"error": "No image provided."}, status=400)

    # Validate file size (5MB max)
    if image.size > 5 * 1024 * 1024:
        return JsonResponse({"error": "Image too large. Maximum 5MB."}, status=400)

    # Validate content type
    allowed_types = ("image/jpeg", "image/png", "image/webp", "image/gif")
    if image.content_type not in allowed_types:
        return JsonResponse(
            {"error": "Invalid image type. Use JPEG, PNG, WebP, or GIF."},
            status=400,
        )

    # Delete old image if exists
    if npc.image:
        old_path = npc.image.path
        if os.path.exists(old_path):
            os.remove(old_path)

    npc.image = image
    npc.save()
    return JsonResponse({"image": npc.image.url})
