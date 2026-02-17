import json

from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods

from .models import Character
from .serializers import serialize_character, serialize_character_summary


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
    return JsonResponse(serialize_character(character), status=201)


@login_required
@require_http_methods(["GET", "PUT", "DELETE"])
def api_character_detail(request, pk):
    """GET: full character data. PUT: update (owner only). DELETE: admin only."""
    character = get_object_or_404(Character, pk=pk)

    if request.method == "GET":
        return JsonResponse(serialize_character(character))

    if request.method == "PUT":
        # Only owner or admin can update
        if request.user != character.owner and not request.user.is_superuser:
            return JsonResponse({"error": "ACCESS DENIED."}, status=403)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid data stream."}, status=400)

        # Update simple text fields
        for field in ("name", "concept", "chronicle", "virtue", "vice"):
            if field in data:
                setattr(character, field, data[field])

        # Update JSON fields
        if "attributes" in data:
            character.attributes = data["attributes"]
        if "skills" in data:
            character.skills = data["skills"]
        if "merits" in data:
            character.merits = data["merits"]
        if "flaws" in data:
            character.flaws = data["flaws"]
        if "pullingStrings" in data:
            character.pulling_strings = data["pullingStrings"]
        if "inventory" in data:
            character.inventory = data["inventory"]

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
        if "willpower" in data:
            character.willpower_current = data["willpower"].get(
                "current", character.willpower_current
            )

        character.save()
        return JsonResponse(serialize_character(character))

    if request.method == "DELETE":
        # Only admin can delete
        if not request.user.is_superuser:
            return JsonResponse({"error": "ACCESS DENIED. Administrator clearance required."}, status=403)
        character.delete()
        return JsonResponse({"status": "Record terminated."})
