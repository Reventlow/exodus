"""Admin registration for the personal combat app.

Phase 0: simple ModelAdmin subclasses with sensible list/filter/search
fields. The admin is the primary mutation surface in Phase 0 — the
REST API for encounters lands in Phase 1.
"""

from django.contrib import admin

from .models import CombatLog, Encounter, Participant


class ParticipantInline(admin.TabularInline):
    """Inline editor for participants on the encounter detail page."""

    model = Participant
    extra = 0
    fields = [
        "name", "participant_kind", "faction",
        "health_bashing", "health_lethal", "health_aggravated", "health_max",
        "willpower_current", "willpower_max",
        "position_label", "position_order",
    ]
    readonly_fields = ["created_at"]
    show_change_link = True


@admin.register(Encounter)
class EncounterAdmin(admin.ModelAdmin):
    list_display = [
        "id", "title", "status", "round_number", "gm", "created_at",
    ]
    list_filter = ["status"]
    search_fields = ["title", "scene_description", "location_text"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [ParticipantInline]


@admin.register(Participant)
class ParticipantAdmin(admin.ModelAdmin):
    list_display = [
        "id", "encounter", "name", "participant_kind", "faction",
        "health_bashing", "health_lethal", "health_aggravated",
    ]
    list_filter = ["participant_kind", "faction", "cover_state"]
    search_fields = ["name", "notes"]
    readonly_fields = ["created_at"]
    autocomplete_fields = []  # Character/NPC admins do not declare search_fields globally; keep blank.


@admin.register(CombatLog)
class CombatLogAdmin(admin.ModelAdmin):
    list_display = [
        "id", "encounter", "sequence", "round_number", "action_type",
        "actor_participant", "created_at",
    ]
    list_filter = ["action_type", "is_reverted"]
    search_fields = ["message"]
    readonly_fields = ["created_at"]
