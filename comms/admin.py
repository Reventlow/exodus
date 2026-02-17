"""Admin configuration for the comms application."""

from django.contrib import admin

from .models import Message, Thread, ThreadMembership


class ThreadMembershipInline(admin.TabularInline):
    model = ThreadMembership
    extra = 0
    readonly_fields = ("joined_at", "last_read_at")


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ("sender", "content", "created_at")


@admin.register(Thread)
class ThreadAdmin(admin.ModelAdmin):
    list_display = ("__str__", "creator", "created_at", "updated_at")
    list_filter = ("created_at",)
    search_fields = ("title", "creator__username")
    inlines = [ThreadMembershipInline, MessageInline]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("sender", "thread", "content_preview", "created_at")
    list_filter = ("created_at",)
    search_fields = ("content", "sender__username")

    @admin.display(description="Content")
    def content_preview(self, obj):
        return obj.content[:80] + "..." if len(obj.content) > 80 else obj.content
