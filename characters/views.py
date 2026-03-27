import json
import os

from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods

from django.db import transaction

from .models import Character, CharacterPullingString, CharacterMerit, XpTransferLog
from .serializers import serialize_character, serialize_character_summary
from agencies.models import Agency
from exodus.models import MeritDefinition, PullingString


# ---------------------------------------------------------------------------
# Page views (return HTML)
# ---------------------------------------------------------------------------

@login_required
def character_list_page(request):
    """Dashboard showing all characters."""
    return render(request, "characters/list.html")


@login_required
def character_sheet_page(request, pk):
    """Character sheet page. Editable for owner, read-only for others."""
    character = get_object_or_404(Character, pk=pk)
    is_owner = request.user == character.owner or request.user.is_superuser
    template = "characters/sheet.html" if is_owner else "characters/view.html"
    return render(request, template, {
        "character_id": character.id,
        "is_owner": is_owner,
        "is_superuser": request.user.is_superuser,
    })


# ---------------------------------------------------------------------------
# API views (return JSON)
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["GET", "POST"])
def api_character_list(request):
    """GET: list all characters. POST: create a new character."""
    if request.method == "GET":
        characters = Character.objects.select_related("owner").all()
        data = [serialize_character_summary(c) for c in characters]
        return JsonResponse(data, safe=False)

    # POST - create new character
    # Non-admin users can only have one character
    if not request.user.is_superuser:
        if Character.objects.filter(owner=request.user).exists():
            return JsonResponse(
                {"error": "Operative already has an active record. Only administrators may create additional records."},
                status=400,
            )

    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        body = {}

    character = Character.objects.create(
        owner=request.user,
        name=body.get("name", "UNKNOWN AGENT"),
    )
    return JsonResponse(serialize_character(character, request.user), status=201)


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
def api_character_detail(request, pk):
    """GET: full character data. PUT: update (owner only). DELETE: admin only."""
    character = get_object_or_404(Character, pk=pk)

    if request.method == "GET":
        return JsonResponse(serialize_character(character, request.user))

    if request.method == "PUT":
        # Only owner or admin can update
        if request.user != character.owner and not request.user.is_superuser:
            return JsonResponse({"error": "ACCESS DENIED."}, status=403)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid data stream."}, status=400)

        # Update simple text fields
        for field in ("name", "concept", "chronicle", "virtue", "vice", "dossier"):
            if field in data:
                setattr(character, field, data[field])
        if "classifiedNotes" in data:
            character.classified_notes = data["classifiedNotes"]

        # Update class — non-superusers cannot set AI
        if "characterClass" in data:
            valid_classes = [c[0] for c in Character.CLASS_CHOICES]
            new_class = data["characterClass"]
            if new_class in valid_classes:
                if new_class == "ai" and not request.user.is_superuser:
                    pass  # Non-admins cannot set AI class
                else:
                    character.character_class = new_class
            elif new_class == "":
                character.character_class = ""

        # Update JSON fields
        if "attributes" in data:
            character.attributes = data["attributes"]
        if "skills" in data:
            character.skills = data["skills"]
        # Add a merit (creates through-table entry)
        if "addMerit" in data:
            merit_id = data["addMerit"].get("meritId")
            rating = data["addMerit"].get("rating", 1)
            try:
                merit = MeritDefinition.objects.get(pk=merit_id)
                rating = max(merit.min_cost, min(merit.cost, rating))
                if not CharacterMerit.objects.filter(
                    character=character, merit=merit
                ).exists():
                    CharacterMerit.objects.create(
                        character=character, merit=merit, rating=rating
                    )
            except MeritDefinition.DoesNotExist:
                pass

        # Remove a merit (by through-table ID)
        if "removeMerit" in data:
            CharacterMerit.objects.filter(
                pk=data["removeMerit"], character=character
            ).delete()

        # Update merit rating
        if "updateMeritRating" in data:
            cm_id = data["updateMeritRating"].get("id")
            new_rating = data["updateMeritRating"].get("rating", 1)
            try:
                cm = CharacterMerit.objects.select_related("merit").get(
                    pk=cm_id, character=character
                )
                cm.rating = max(cm.merit.min_cost, min(cm.merit.cost, new_rating))
                cm.save()
            except CharacterMerit.DoesNotExist:
                pass
        if "flaws" in data:
            character.flaws = data["flaws"]
        # Add a pulling string (creates through-table entry)
        if "addPullingString" in data:
            ps_id = data["addPullingString"].get("pullingStringId")
            npc_id = data["addPullingString"].get("linkedNpcId")
            try:
                ps = PullingString.objects.get(pk=ps_id)
                # Non-linkable: only one instance per character
                if not ps.is_linkable:
                    if not CharacterPullingString.objects.filter(
                        character=character, pulling_string=ps
                    ).exists():
                        cps = CharacterPullingString(character=character, pulling_string=ps)
                        if npc_id:
                            from npcs.models import NPC
                            cps.linked_npc = NPC.objects.filter(pk=npc_id).first()
                        cps.save()
                else:
                    # Linkable: can have multiple (each linked to a different NPC)
                    cps = CharacterPullingString(character=character, pulling_string=ps)
                    if npc_id:
                        from npcs.models import NPC
                        cps.linked_npc = NPC.objects.filter(pk=npc_id).first()
                    cps.save()
            except PullingString.DoesNotExist:
                pass

        # Remove a pulling string (by through-table ID)
        if "removePullingString" in data:
            cps_id = data["removePullingString"]
            CharacterPullingString.objects.filter(
                pk=cps_id, character=character
            ).delete()

        # Link/unlink NPC on an existing pulling string entry
        if "linkNpc" in data:
            cps_id = data["linkNpc"].get("id")
            npc_id = data["linkNpc"].get("npcId")
            try:
                cps = CharacterPullingString.objects.get(pk=cps_id, character=character)
                if npc_id:
                    from npcs.models import NPC
                    cps.linked_npc = NPC.objects.filter(pk=npc_id).first()
                else:
                    cps.linked_npc = None
                cps.save()
            except CharacterPullingString.DoesNotExist:
                pass
        if "inventory" in data:
            character.inventory = data["inventory"]
        if "specialisations" in data:
            character.specialisations = data["specialisations"]

        # Update health
        if "health" in data:
            health = data["health"]
            character.health_bashing = health.get("bashing", character.health_bashing)
            character.health_lethal = health.get("lethal", character.health_lethal)
            character.health_aggravated = health.get("aggravated", character.health_aggravated)

        # Update numeric fields
        if "size" in data:
            character.size = data["size"]
        if "mentalLoad" in data:
            character.mental_load = max(0, min(6, data["mentalLoad"]))
        if "experience" in data:
            character.experience = data["experience"]
        if "experienceUsed" in data:
            character.experience_used = data["experienceUsed"]
        if "willpower" in data:
            character.willpower_current = data["willpower"].get(
                "current", character.willpower_current
            )

        character.save()
        return JsonResponse(serialize_character(character, request.user))

    if request.method == "DELETE":
        # Only admin can delete
        if not request.user.is_superuser:
            return JsonResponse({"error": "ACCESS DENIED. Administrator clearance required."}, status=403)
        character.delete()
        return JsonResponse({"status": "Record terminated."})


@login_required
@require_http_methods(["POST"])
def api_character_image(request, pk):
    """Upload character profile picture."""
    character = get_object_or_404(Character, pk=pk)

    # Only owner or admin can upload
    if request.user != character.owner and not request.user.is_superuser:
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
    if character.profile_picture:
        old_path = character.profile_picture.path
        if os.path.exists(old_path):
            os.remove(old_path)

    character.profile_picture = image
    character.save()
    return JsonResponse({"profilePicture": character.profile_picture.url})


@login_required
@require_http_methods(["POST"])
def api_transfer_xp(request, pk):
    """Transfer XP from character to agency. 1 character XP = 10 agency XP."""
    character = get_object_or_404(Character, pk=pk)

    if request.user != character.owner and not request.user.is_superuser:
        return JsonResponse({"error": "ACCESS DENIED."}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid data stream."}, status=400)

    amount = data.get("amount", 0)
    agency_id = data.get("agencyId")

    if not isinstance(amount, int) or amount < 1:
        return JsonResponse({"error": "Amount must be a positive integer."}, status=400)

    if amount > character.experience:
        return JsonResponse(
            {"error": f"Insufficient XP. Character has {character.experience}."},
            status=400,
        )

    agency = get_object_or_404(Agency, pk=agency_id, is_player_agency=True)

    with transaction.atomic():
        character.experience -= amount
        character.save()
        agency.experience += amount * 10
        agency.save()
        XpTransferLog.objects.create(
            character=character,
            agency=agency,
            amount=amount,
            agency_received=amount * 10,
        )

    return JsonResponse({
        "status": "Transfer complete.",
        "characterXp": character.experience,
        "agencyXp": agency.experience,
        "transferred": amount,
        "agencyReceived": amount * 10,
    })
