"""Admin configuration for core Exodus models."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from .models import SiteSettings


# Customize the User admin list display
admin.site.unregister(User)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = (
        "username", "email", "is_active", "is_staff", "is_superuser", "last_login",
    )
    list_filter = ("is_active", "is_staff", "is_superuser")


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    """Admin for the SiteSettings singleton."""

    list_display = ("__str__", "next_game_date")

    def has_add_permission(self, request):
        """Prevent creating more than one instance."""
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of the singleton."""
        return False
