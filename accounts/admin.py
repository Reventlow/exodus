"""Admin registration for the accounts app."""

from datetime import timedelta

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.html import format_html

from .models import UserProfile


# Activity windows — must mirror the thresholds in accounts/views.py
# (ACTIVE/STANDBY/DORMANT/INACTIVE @ 2h / 4h / 2d / >2d).
_WINDOWS = (
    (timedelta(hours=2), "ACTIVE", "#39ff7a"),
    (timedelta(hours=4), "STANDBY", "#ffb454"),
    (timedelta(days=2), "DORMANT", "#6c8aa0"),
)
_INACTIVE = ("INACTIVE", "#4a5568")


def _activity_status(last_activity):
    """Return (label, color) for the given last_activity timestamp."""
    if last_activity is None:
        return _INACTIVE
    delta = timezone.now() - last_activity
    for window, label, color in _WINDOWS:
        if delta <= window:
            return label, color
    return _INACTIVE


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """Standalone UserProfile admin with activity monitoring."""

    list_display = (
        "user", "activity_status", "last_activity",
        "since", "has_avatar",
    )
    list_filter = ("last_activity",)
    search_fields = ("user__username", "user__email")
    readonly_fields = ("last_activity",)
    ordering = ("-last_activity",)

    @admin.display(description="STATUS", ordering="last_activity")
    def activity_status(self, obj):
        label, color = _activity_status(obj.last_activity)
        return format_html(
            '<span style="display:inline-block;padding:2px 8px;'
            'border:1px solid {0};color:{0};font-family:monospace;'
            'font-size:11px;letter-spacing:0.16em;">{1}</span>',
            color, label,
        )

    @admin.display(description="Since")
    def since(self, obj):
        if obj.last_activity is None:
            return "—"
        delta = timezone.now() - obj.last_activity
        s = int(delta.total_seconds())
        if s < 60:
            return f"{s}s"
        if s < 3600:
            return f"{s // 60}m"
        if s < 86400:
            return f"{s // 3600}h {(s % 3600) // 60}m"
        return f"{s // 86400}d {(s % 86400) // 3600}h"

    @admin.display(description="Avatar", boolean=True)
    def has_avatar(self, obj):
        return bool(obj.avatar)


class UserProfileInline(admin.StackedInline):
    """Show profile + activity inline on the User admin page."""

    model = UserProfile
    can_delete = False
    verbose_name_plural = "Profile"
    readonly_fields = ("last_activity",)
    fk_name = "user"


class UserAdmin(DjangoUserAdmin):
    """Extend Django's User admin with the profile inline + activity column."""

    inlines = (UserProfileInline,)
    list_display = DjangoUserAdmin.list_display + ("activity_status",)

    @admin.display(description="STATUS")
    def activity_status(self, obj):
        try:
            profile = obj.profile
        except UserProfile.DoesNotExist:
            label, color = _INACTIVE
        else:
            label, color = _activity_status(profile.last_activity)
        return format_html(
            '<span style="display:inline-block;padding:2px 8px;'
            'border:1px solid {0};color:{0};font-family:monospace;'
            'font-size:11px;letter-spacing:0.16em;">{1}</span>',
            color, label,
        )


# Re-register the User admin with our extended one.
admin.site.unregister(User)
admin.site.register(User, UserAdmin)
