from django.contrib import admin
from .models import Agency, ChangeRequest, GlobalFlaw, FTLProject, AgencyFTLProject, CouncilItem


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


@admin.register(GlobalFlaw)
class GlobalFlawAdmin(admin.ModelAdmin):
    list_display = ("name", "value", "order", "updated_at")
    search_fields = ("name", "description")
    ordering = ("order", "name")


@admin.register(FTLProject)
class FTLProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "required_successes", "updated_at")
    search_fields = ("name", "description")


@admin.register(AgencyFTLProject)
class AgencyFTLProjectAdmin(admin.ModelAdmin):
    list_display = ("agency", "ftl_project", "current_successes", "assigned_at")
    list_filter = ("agency", "ftl_project")
    search_fields = ("agency__name", "ftl_project__name")


@admin.register(CouncilItem)
class CouncilItemAdmin(admin.ModelAdmin):
    list_display = ("name", "item_type", "status", "proposed_by", "order", "updated_at")
    list_filter = ("item_type", "status")
    search_fields = ("name", "description", "proposed_by")
