from django.contrib import admin

from .models import CampaignSession, StoryIdea, TimelineEvent


@admin.register(StoryIdea)
class StoryIdeaAdmin(admin.ModelAdmin):
    list_display = ["title", "pinned", "is_shared", "updated_at"]
    list_filter = ["pinned"]
    search_fields = ["title", "content", "tags"]
    filter_horizontal = ["shared_with"]

    @admin.display(boolean=True, description="Shared")
    def is_shared(self, obj):
        return obj.shared_with.exists()


@admin.register(TimelineEvent)
class TimelineEventAdmin(admin.ModelAdmin):
    list_display = ["title", "event_type", "game_date", "game_date_sort", "updated_at"]
    list_filter = ["event_type"]
    search_fields = ["title", "description", "tags"]


@admin.register(CampaignSession)
class CampaignSessionAdmin(admin.ModelAdmin):
    list_display = ["session_number", "title", "played_at", "game_date"]
    search_fields = ["title", "summary", "tags"]
    ordering = ["session_number"]
