"""
Models for the comms (in-game messaging) application.

Thread-based conversations with membership tracking and unread counts.
"""

from django.contrib.auth.models import User
from django.db import models


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
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.sender.username}: {self.content[:50]}"
