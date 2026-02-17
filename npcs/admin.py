from django.contrib import admin
from .models import NPC


@admin.register(NPC)
class NPCAdmin(admin.ModelAdmin):
    list_display = ("name", "state", "occupation", "assigned_to", "updated_at")
    list_filter = ("state", "assigned_to")
    search_fields = ("name", "occupation", "nationality", "assigned_to__username")
