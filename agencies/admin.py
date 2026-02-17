from django.contrib import admin
from .models import Agency, ChangeRequest


@admin.register(Agency)
class AgencyAdmin(admin.ModelAdmin):
    list_display = ("name", "is_player_agency", "integrity", "experience", "updated_at")
    list_filter = ("is_player_agency",)
    search_fields = ("name", "alliance", "headquarters")


@admin.register(ChangeRequest)
class ChangeRequestAdmin(admin.ModelAdmin):
    list_display = ("field_name", "agency", "requester", "status", "created_at")
    list_filter = ("status", "agency")
    search_fields = ("field_name", "description", "requester__username")
