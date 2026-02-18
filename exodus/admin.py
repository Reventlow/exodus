"""Admin configuration for core Exodus models."""

from django.contrib import admin

from .models import SiteSettings


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
