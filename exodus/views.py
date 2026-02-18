"""Core views for Exodus site settings."""

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect, render

from .models import SiteSettings


@staff_member_required
def site_settings(request):
    """Allow staff to update site-wide settings."""
    settings_obj = SiteSettings.load()

    if request.method == "POST":
        date_value = request.POST.get("next_game_date", "").strip()
        settings_obj.next_game_date = date_value or None
        settings_obj.save()
        messages.success(request, "Settings updated.")
        return redirect("site-settings")

    return render(request, "site_settings.html", {"settings_obj": settings_obj})
