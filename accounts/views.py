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
from django.views.decorators.http import require_http_methods


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
    """Snapshot the roster shown on the Clearance Gate login.

    One row per user (active or burned), using their first character's
    name. Superusers appear as ``GM``. Burned operatives (``User.is_active
    = False`` — left the group, kept for historical record) appear at the
    bottom of the list with status ``BURNED``.

    A synthetic ``__SYSTEM__`` row is always appended with status
    ``CRAWLING`` and role ``SYSTEMS SECURITY`` — the in-fiction systems-
    security daemon that never logs off. Excluded from the active-count
    badge.

    Sorted by status priority then codename. Returns
    ``(rows, active_count)``.
    """
    now = timezone.now()
    sort_order = {
        "ACTIVE": 0, "STANDBY": 1, "DORMANT": 2,
        "CRAWLING": 3, "INACTIVE": 4, "BURNED": 5,
    }
    rows = []
    users = (
        User.objects.all()
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
        # is_active=False overrides the time-based status — the operative
        # has been removed from the roster but the row stays for the
        # in-fiction "burned" tag.
        if not u.is_active:
            status = "BURNED"
        else:
            status = _compute_activity_status(last, now)
        delta_sec = (now - last).total_seconds() if last else None
        rows.append({
            "codename": codename,
            "status": status,
            "node": node,
            "uplink": _format_since(delta_sec),
        })
    # Always-on synthetic SYSTEM row. Not a real user — this is the
    # systems-security daemon. Always CRAWLING, always there.
    rows.append({
        "codename": "__SYSTEM__",
        "status": "CRAWLING",
        "node": "SYSTEMS SECURITY",
        "uplink": "ALWAYS",
    })
    rows.sort(key=lambda r: (sort_order[r["status"]], r["codename"]))
    # Active count counts real humans only; the SYSTEM row is decorative.
    active_count = sum(
        1 for r in rows
        if r["status"] == "ACTIVE" and r["codename"] != "__SYSTEM__"
    )
    return rows, active_count


def _serialize_user(user, now=None):
    """Serialize a user with profile + activity status for the admin API."""
    if now is None:
        now = timezone.now()
    profile = getattr(user, "profile", None)
    last = profile.last_activity if profile else None
    char = (
        user.characters.first()
        if (hasattr(user, "characters") and not user.is_superuser)
        else None
    )
    delta_sec = (now - last).total_seconds() if last else None
    return {
        "username": user.username,
        "isSuperuser": user.is_superuser,
        "isActive": user.is_active,
        "email": user.email,
        "dateJoined": user.date_joined.isoformat() if user.date_joined else None,
        "lastLogin": user.last_login.isoformat() if user.last_login else None,
        "lastActivity": last.isoformat() if last else None,
        "secondsSinceActivity": int(delta_sec) if delta_sec is not None else None,
        "activityStatus": (
            "BURNED" if not user.is_active
            else _compute_activity_status(last, now)
        ),
        "burned": not user.is_active,
        "characterName": char.name if char else None,
        "characterClass": char.character_class if char else None,
        "hasAvatar": bool(profile and profile.avatar) if profile else False,
    }


@require_http_methods(["GET"])
def api_admin_list_user_profiles(request):
    """List all users with profile data + activity status (admin-only)."""
    if not request.user.is_superuser:
        return JsonResponse({"error": "Forbidden"}, status=403)
    now = timezone.now()
    users = (
        User.objects.all()
        .select_related("profile")
        .prefetch_related("characters")
        .order_by("-is_superuser", "username")
    )
    payload = [_serialize_user(u, now) for u in users]
    return JsonResponse({"count": len(payload), "users": payload})


@require_http_methods(["GET"])
def api_admin_get_user_profile(request, username):
    """Get a single user's profile + activity status (admin-only)."""
    if not request.user.is_superuser:
        return JsonResponse({"error": "Forbidden"}, status=403)
    try:
        user = (
            User.objects
            .select_related("profile")
            .prefetch_related("characters")
            .get(username=username)
        )
    except User.DoesNotExist:
        return JsonResponse({"error": "User not found"}, status=404)
    return JsonResponse(_serialize_user(user))


@require_http_methods(["POST"])
def api_admin_set_user_active(request, username):
    """Toggle a user's ``is_active`` flag (burn / un-burn). Admin-only.

    POST body: ``{"active": true | false}``.
    """
    if not request.user.is_superuser:
        return JsonResponse({"error": "Forbidden"}, status=403)
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    if "active" not in body:
        return JsonResponse({"error": "Missing 'active' boolean"}, status=400)
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        return JsonResponse({"error": "User not found"}, status=404)
    user.is_active = bool(body["active"])
    user.save(update_fields=["is_active"])
    return JsonResponse(_serialize_user(user))


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


@require_http_methods(["POST"])
def api_admin_set_last_activity(request):
    """Admin-only bulk-set ``UserProfile.last_activity`` for testing the
    roster status pills. POST JSON body:

        {"users": "all_non_superuser" | ["username1", ...],
         "timestamp": "2026-04-13T13:00:00+00:00"}

    Returns ``{"updated": N, "usernames": [...]}``. Authenticated as a
    superuser via session, or via the MCP Bearer token middleware.
    """
    from datetime import datetime

    if not request.user.is_superuser:
        return JsonResponse({"error": "Forbidden"}, status=403)
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    raw_ts = body.get("timestamp")
    try:
        ts = datetime.fromisoformat(raw_ts) if raw_ts else None
    except (TypeError, ValueError):
        ts = None
    if ts is None:
        return JsonResponse(
            {"error": "Invalid or missing 'timestamp' (ISO 8601 required)."},
            status=400,
        )
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    target = body.get("users")
    if target == "all_non_superuser":
        users_qs = User.objects.filter(is_superuser=False, is_active=True)
    elif isinstance(target, list) and all(isinstance(u, str) for u in target):
        users_qs = User.objects.filter(username__in=target, is_active=True)
    else:
        return JsonResponse(
            {"error": "'users' must be \"all_non_superuser\" or a list of usernames."},
            status=400,
        )

    from .models import UserProfile

    updated = []
    for user in users_qs:
        profile, _ = UserProfile.objects.get_or_create(user=user)
        UserProfile.objects.filter(pk=profile.pk).update(last_activity=ts)
        updated.append(user.username)
    return JsonResponse({
        "updated": len(updated),
        "usernames": updated,
        "timestamp": ts.isoformat(),
    })


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
