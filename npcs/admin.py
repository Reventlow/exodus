from django.contrib import admin
from .models import NPC, NPCNote


@admin.register(NPC)
class NPCAdmin(admin.ModelAdmin):
    list_display = (
        "name", "is_npc_dossier", "state", "occupation",
        "agency", "assigned_to", "updated_at",
    )
    list_filter = ("is_npc_dossier", "state", "agency", "assigned_to")
    search_fields = (
        "name", "occupation", "nationality",
        "assigned_to__username", "agency__name",
    )


@admin.register(NPCNote)
class NPCNoteAdmin(admin.ModelAdmin):
    list_display = ("npc", "author", "created_at")
    list_filter = ("author",)
    search_fields = ("npc__name", "author__username", "text")
