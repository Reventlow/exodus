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
    return {
        "tweaks": tweaks,
        "tweaks_json": json.dumps(tweaks),
        "next_url_json": json.dumps(request.GET.get("next") or "/"),
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
