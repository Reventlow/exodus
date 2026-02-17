from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.contrib import messages


def login_view(request):
    """Authenticate user and redirect to dashboard."""
    if request.user.is_authenticated:
        return redirect("/")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            next_url = request.GET.get("next", "/")
            return redirect(next_url)
        else:
            messages.error(request, "ACCESS DENIED. Invalid credentials.")

    return render(request, "accounts/login.html")


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
            user = User.objects.create_user(username=username, password=password)
            login(request, user)
            messages.success(request, "OPERATIVE REGISTERED. Welcome, Agent.")
            return redirect("/")

    return render(request, "accounts/register.html")


@login_required
def profile_view(request):
    """Show profile info and password change form."""
    if request.method == "POST":
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            # Keep the user logged in after password change
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

    return render(request, "accounts/profile.html", {"form": form})
