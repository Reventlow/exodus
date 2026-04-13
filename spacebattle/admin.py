"""Admin registration for the spacebattle app."""

from django.contrib import admin

from .models import Battle, BattleLog, BattleParticipant


class BattleParticipantInline(admin.TabularInline):
    model = BattleParticipant
    extra = 0
    readonly_fields = ["created_at"]


@admin.register(Battle)
class BattleAdmin(admin.ModelAdmin):
    list_display = [
        "name", "status", "round_number", "grid_width", "grid_height",
        "created_by", "created_at",
    ]
    list_filter = ["status"]
    search_fields = ["name", "notes"]
    inlines = [BattleParticipantInline]


@admin.register(BattleParticipant)
class BattleParticipantAdmin(admin.ModelAdmin):
    list_display = [
        "battle", "starship", "side", "q", "r", "facing", "status",
        "initiative_result",
    ]
    list_filter = ["battle", "side", "status"]
    search_fields = ["starship__name"]


@admin.register(BattleLog)
class BattleLogAdmin(admin.ModelAdmin):
    list_display = [
        "battle", "round_number", "action_type",
        "actor_participant", "is_reverted", "created_at",
    ]
    list_filter = ["battle", "action_type", "is_reverted"]
    search_fields = ["message"]
