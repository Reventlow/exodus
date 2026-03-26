"""
Models for the comms (in-game messaging) application.

Thread-based conversations with membership tracking and unread counts.
"""

from django.contrib.auth.models import User
from django.db import models

POSTED_AS_TYPE_CHOICES = [
    ("", "Self"),
    ("character", "Character"),
    ("npc", "NPC"),
]


class Thread(models.Model):
    """A conversation thread with one or more members."""

    title = models.CharField(max_length=200, blank=True)
    creator = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_threads",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.title or f"Thread #{self.pk}"


class ThreadMembership(models.Model):
    """Tracks which users belong to which threads."""

    thread = models.ForeignKey(
        Thread,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="thread_memberships",
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    last_read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("thread", "user")

    def __str__(self) -> str:
        return f"{self.user.username} in {self.thread}"


class Message(models.Model):
    """A single message within a thread."""

    thread = models.ForeignKey(
        Thread,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="sent_messages",
    )
    content = models.TextField(blank=True, default="")
    image = models.ImageField(upload_to="comms_images/", blank=True, null=True)
    posted_as_type = models.CharField(
        max_length=20, choices=POSTED_AS_TYPE_CHOICES, blank=True, default="",
        help_text="If set, the message is displayed as this dossier instead of the sender.",
    )
    posted_as_id = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="PK of the Character or NPC being impersonated.",
    )
    posted_as_name = models.CharField(
        max_length=200, blank=True, default="",
        help_text="Denormalized display name for the impersonated dossier.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        name = self.posted_as_name or self.sender.username
        return f"{name}: {self.content[:50]}"
