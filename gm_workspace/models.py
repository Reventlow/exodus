"""Models for the GM Workspace."""
from django.conf import settings
from django.db import models


class StoryIdea(models.Model):
    """A GM-only plot / story idea note, optionally shared with specific players as a brief."""

    title = models.CharField(max_length=300)
    content = models.TextField(blank=True, default="", help_text="Markdown")
    tags = models.CharField(
        max_length=500, blank=True, default="",
        help_text="Comma-separated free-text tags.",
    )
    pinned = models.BooleanField(default=False)

    # Per-note sharing. Empty = GM-only. Populated = those users can READ (never edit).
    shared_with = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True,
        related_name="shared_story_ideas",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_story_ideas",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-pinned", "-updated_at"]

    def __str__(self):
        return self.title or f"StoryIdea #{self.pk}"

    @property
    def is_shared(self):
        return self.shared_with.exists()


class TimelineEvent(models.Model):
    """A chronological beat in the campaign — session, plot event, world event, or freeform note."""

    EVENT_TYPES = [
        ("session", "Session"),
        ("plot", "Plot Beat"),
        ("world", "World Event"),
        ("note", "Note"),
    ]

    title = models.CharField(max_length=300)
    description = models.TextField(blank=True, default="", help_text="Markdown")
    event_type = models.CharField(
        max_length=20, choices=EVENT_TYPES, default="note",
    )
    game_date = models.CharField(
        max_length=100, blank=True, default="",
        help_text="Human-readable in-game date (e.g. '13 May 2036').",
    )
    game_date_sort = models.DateTimeField(
        null=True, blank=True,
        help_text="Sortable datetime, auto-derived from game_date.",
    )
    tags = models.CharField(
        max_length=500, blank=True, default="",
        help_text="Comma-separated free-text tags.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_timeline_events",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-game_date_sort", "-updated_at"]

    def __str__(self):
        return self.title or f"TimelineEvent #{self.pk}"


class CampaignSession(models.Model):
    """A single session's recap — session number, date, summary."""

    session_number = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Sequential session number. Leave blank for one-offs.",
    )
    title = models.CharField(max_length=300)
    summary = models.TextField(blank=True, default="", help_text="Markdown recap")
    played_at = models.DateField(
        null=True, blank=True,
        help_text="Real-world date the session was played.",
    )
    game_date = models.CharField(
        max_length=100, blank=True, default="",
        help_text="In-game date(s) covered by the session.",
    )
    tags = models.CharField(
        max_length=500, blank=True, default="",
        help_text="Comma-separated free-text tags.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_campaign_sessions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["session_number", "-played_at"]

    def __str__(self):
        if self.session_number:
            return f"Session {self.session_number}: {self.title}"
        return self.title or f"CampaignSession #{self.pk}"
