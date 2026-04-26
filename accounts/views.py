"""Authentication views — login, logout, registration, profile.

The login surface (Clearance Gate) supports two response modes:
- HTML (default): legacy, full-page redirects + ``messages`` errors,
  works without JS so the bare ``<form method="POST">`` always functions.
- JSON (when caller sends ``Accept: application/json`` or
  ``X-Requested-With: XMLHttpRequest``): the front-end fetch() call
  drives the cinematic auth animation only after the server confirms
  success or failure. Returns ``{ok: True, redirect: "..."}`` or
  ``{ok: False, error: "..."}``.
"""

import json

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone


# Activity-status thresholds. ACTIVE within 2h, STANDBY within 4h,
# DORMANT within 2 days, INACTIVE thereafter (or never seen).
ACTIVE_WINDOW_SEC = 2 * 60 * 60
STANDBY_WINDOW_SEC = 4 * 60 * 60
DORMANT_WINDOW_SEC = 2 * 24 * 60 * 60


def _compute_activity_status(last_activity, now):
    """Map a UserProfile.last_activity datetime to a status label."""
    if last_activity is None:
        return "INACTIVE"
    delta = (now - last_activity).total_seconds()
    if delta <= ACTIVE_WINDOW_SEC:
        return "ACTIVE"
    if delta <= STANDBY_WINDOW_SEC:
        return "STANDBY"
    if delta <= DORMANT_WINDOW_SEC:
        return "DORMANT"
    return "INACTIVE"


def _format_since(delta_seconds):
    """Compact 'time since' string for the uplink column."""
    if delta_seconds is None:
        return "—"
    s = int(delta_seconds)
    if s < 3600:
        return f"{s // 60:02d}:{s % 60:02d}"
    if s < 86400:
        return f"{s // 3600:02d}:{(s % 3600) // 60:02d}"
    days = s // 86400
    return f"{days}d {(s % 86400) // 3600}h"


def _build_login_roster():
    """Snapshot the active roster shown on the Clearance Gate login.

    One row per active player using their first character's name.
    Superusers appear as ``GM``. Sorted by activity status priority
    then codename. Returns ``(rows, active_count)``.
    """
    now = timezone.now()
    sort_order = {"ACTIVE": 0, "STANDBY": 1, "DORMANT": 2, "INACTIVE": 3}
    rows = []
    users = (
        User.objects.filter(is_active=True)
        .select_related("profile")
        .prefetch_related("characters")
    )
    for u in users:
        profile = getattr(u, "profile", None)
        last = profile.last_activity if profile else None
        if u.is_superuser:
            codename = "GM"
            node = "DIRECTOR"
        else:
            char = u.characters.first()
            if char and char.name and char.name != "UNKNOWN AGENT":
                codename = char.name.upper()
                node = (char.character_class or "").upper() or "—"
            else:
                codename = u.username.upper()
                node = "—"
        status = _compute_activity_status(last, now)
        delta_sec = (now - last).total_seconds() if last else None
        rows.append({
            "codename": codename,
            "status": status,
            "node": node,
            "uplink": _format_since(delta_sec),
        })
    rows.sort(key=lambda r: (sort_order[r["status"]], r["codename"]))
    active_count = sum(1 for r in rows if r["status"] == "ACTIVE")
    return rows, active_count


def _wants_json(request):
    """Detect AJAX/JSON callers from the Clearance Gate JS."""
    accept = request.headers.get("Accept", "")
    xrw = request.headers.get("X-Requested-With", "")
    return ("application/json" in accept) or (xrw == "XMLHttpRequest")


def _login_context(request):
    """Shared template context for the Clearance Gate login + register."""
    from exodus.models import SiteSettings
    settings_obj = SiteSettings.load()
    tweaks = settings_obj.get_tweaks()
    roster, active_count = _build_login_roster()
    return {
        "tweaks": tweaks,
        "tweaks_json": json.dumps(tweaks),
        "next_url_json": json.dumps(request.GET.get("next") or "/"),
        "roster": roster,
        "roster_active_count": active_count,
        "roster_total": len(roster),
    }


def login_view(request):
    """Authenticate user and redirect to dashboard."""
    if request.user.is_authenticated:
        if _wants_json(request):
            return JsonResponse({"ok": True, "redirect": "/"})
        return redirect("/")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            next_url = request.GET.get("next") or request.POST.get("next") or "/"
            if _wants_json(request):
                return JsonResponse({"ok": True, "redirect": next_url})
            return redirect(next_url)

        # Authentication failed. Decide what error to show.
        try:
            pending = User.objects.get(username=username)
            if not pending.is_active:
                err = "ACCOUNT PENDING. AWAITING ADMINISTRATOR APPROVAL."
            else:
                err = "ACCESS DENIED. INVALID CREDENTIALS."
        except User.DoesNotExist:
            err = "ACCESS DENIED. INVALID CREDENTIALS."

        if _wants_json(request):
            return JsonResponse({"ok": False, "error": err}, status=200)
        messages.error(request, err)

    return render(request, "accounts/login.html", _login_context(request))


def logout_view(request):
    """Logout and redirect to login page."""
    logout(request)
    return redirect("accounts:login")


def register_view(request):
    """Create a new user account."""
    if request.user.is_authenticated:
        return redirect("/")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        password_confirm = request.POST.get("password_confirm", "")

        errors = []
        if not username:
            errors.append("Codename is required.")
        if len(password) < 8:
            errors.append("Passphrase must be at least 8 characters.")
        if password != password_confirm:
            errors.append("Passphrases do not match.")
        if User.objects.filter(username=username).exists():
            errors.append("Codename already in use.")

        if errors:
            for error in errors:
                messages.error(request, error)
        else:
            User.objects.create_user(
                username=username, password=password, is_active=False
            )
            messages.success(
                request,
                "PETITION RECEIVED. Your account requires administrator "
                "approval before access is granted.",
            )
            return redirect("accounts:login")

    return render(request, "accounts/register.html", _login_context(request))


@login_required
def profile_view(request):
    """Show profile info, avatar upload, and password change form."""
    from .models import UserProfile

    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "avatar":
            if "avatar" in request.FILES:
                profile.avatar = request.FILES["avatar"]
                profile.save(update_fields=["avatar"])
                messages.success(request, "Avatar updated.")
            elif request.POST.get("remove_avatar"):
                profile.avatar = None
                profile.save(update_fields=["avatar"])
                messages.success(request, "Avatar removed.")
            return redirect("accounts:profile")

        else:
            form = PasswordChangeForm(request.user, request.POST)
            if form.is_valid():
                user = form.save()
                from django.contrib.auth import update_session_auth_hash
                update_session_auth_hash(request, user)
                messages.success(request, "Passphrase updated successfully.")
                return redirect("accounts:profile")
            else:
                for field, field_errors in form.errors.items():
                    for error in field_errors:
                        messages.error(request, error)
    else:
        form = PasswordChangeForm(request.user)

    return render(request, "accounts/profile.html", {
        "form": form,
        "profile": profile,
    })
