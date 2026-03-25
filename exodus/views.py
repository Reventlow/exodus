"""Core views for Exodus site settings."""

from pathlib import Path

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET

from .models import SiteSettings


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
        },
    })
