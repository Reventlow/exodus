import json
import os

from django.contrib.auth.models import User
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods

from .models import NPC, NPCNote
from .serializers import serialize_npc, serialize_npc_summary, serialize_npc_note
from agencies.models import Agency


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

    if npc.is_npc_dossier:
        # NPC dossiers: only admin can edit fields
        is_editor = request.user.is_superuser
    else:
        # Player contacts: assigned user or admin
        is_editor = request.user == npc.assigned_to or request.user.is_superuser

    is_admin = request.user.is_superuser
    return render(request, "npcs/detail.html", {
        "npc_id": npc.id,
        "is_editor": is_editor,
        "is_admin": is_admin,
        "is_npc_dossier": npc.is_npc_dossier,
    })


# ---------------------------------------------------------------------------
# API views (return JSON)
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["GET", "POST"])
def api_npc_list(request):
    """GET: list all NPCs. POST: create a new NPC."""
    if request.method == "GET":
        npcs = NPC.objects.select_related("assigned_to", "agency").all()
        data = [serialize_npc_summary(n) for n in npcs]
        return JsonResponse(data, safe=False)

    # POST - create new NPC
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        body = {}

    is_npc_dossier = body.get("isNpcDossier", False)

    if is_npc_dossier:
        # Only admins can create NPC dossiers
        if not request.user.is_superuser:
            return JsonResponse(
                {"error": "ACCESS DENIED. Administrator clearance required."},
                status=403,
            )

        # Optionally assign to an agency
        agency = None
        agency_id = body.get("agencyId")
        if agency_id:
            try:
                agency = Agency.objects.get(pk=agency_id, is_player_agency=False)
            except Agency.DoesNotExist:
                pass

        npc = NPC.objects.create(
            name=body.get("name", "UNKNOWN OPERATIVE"),
            is_npc_dossier=True,
            agency=agency,
            created_by=request.user,
        )
    else:
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
        # NPC dossiers: admin only
        if npc.is_npc_dossier:
            if not request.user.is_superuser:
                return JsonResponse({"error": "ACCESS DENIED."}, status=403)
        else:
            # Player contacts: assigned user or admin
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

        # Admin can reassign (player contacts)
        if "assignedToId" in data and request.user.is_superuser:
            if not npc.is_npc_dossier:
                try:
                    new_user = User.objects.get(pk=data["assignedToId"])
                    npc.assigned_to = new_user
                except User.DoesNotExist:
                    pass

        # Admin can assign/change agency (NPC dossiers)
        if "agencyId" in data and request.user.is_superuser and npc.is_npc_dossier:
            if data["agencyId"]:
                try:
                    agency = Agency.objects.get(
                        pk=data["agencyId"], is_player_agency=False
                    )
                    npc.agency = agency
                except Agency.DoesNotExist:
                    pass
            else:
                npc.agency = None

        # Admin transfer: convert between player dossier and NPC dossier
        if "transfer" in data and request.user.is_superuser:
            transfer = data["transfer"]
            target_type = transfer.get("type")  # "player" or "agency"

            if target_type == "player":
                # Transfer to a player — convert to player dossier
                user_id = transfer.get("userId")
                if user_id:
                    try:
                        new_user = User.objects.get(pk=user_id)
                        npc.is_npc_dossier = False
                        npc.assigned_to = new_user
                        npc.agency = None
                    except User.DoesNotExist:
                        pass

            elif target_type == "agency":
                # Transfer to an NPC agency — convert to NPC dossier
                agency_id = transfer.get("agencyId")
                if agency_id:
                    try:
                        agency = Agency.objects.get(
                            pk=agency_id, is_player_agency=False
                        )
                        npc.is_npc_dossier = True
                        npc.agency = agency
                        npc.assigned_to = None
                    except Agency.DoesNotExist:
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

    # Permission check
    if npc.is_npc_dossier:
        if not request.user.is_superuser:
            return JsonResponse({"error": "ACCESS DENIED."}, status=403)
    else:
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


# ---------------------------------------------------------------------------
# NPC Notes API
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["GET", "POST"])
def api_npc_notes(request, pk):
    """GET: list notes. POST: add a note (any authenticated user)."""
    npc = get_object_or_404(NPC, pk=pk)

    if request.method == "GET":
        notes = npc.notes.select_related("author").all()
        return JsonResponse([serialize_npc_note(n) for n in notes], safe=False)

    # POST - create note
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid data stream."}, status=400)

    text = body.get("text", "").strip()
    if not text:
        return JsonResponse({"error": "Note text is required."}, status=400)

    note = NPCNote.objects.create(
        npc=npc,
        author=request.user,
        text=text,
    )
    return JsonResponse(serialize_npc_note(note), status=201)


@login_required
@require_http_methods(["PUT", "DELETE"])
def api_npc_note_detail(request, pk, note_pk):
    """PUT: edit note (author or admin). DELETE: remove note (author or admin)."""
    npc = get_object_or_404(NPC, pk=pk)
    note = get_object_or_404(NPCNote, pk=note_pk, npc=npc)

    # Only author or admin can modify/delete
    if request.user != note.author and not request.user.is_superuser:
        return JsonResponse({"error": "ACCESS DENIED."}, status=403)

    if request.method == "PUT":
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid data stream."}, status=400)

        text = body.get("text", "").strip()
        if not text:
            return JsonResponse({"error": "Note text is required."}, status=400)

        note.text = text
        note.save()
        return JsonResponse(serialize_npc_note(note))

    if request.method == "DELETE":
        note.delete()
        return JsonResponse({"status": "Note deleted."})
