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
    ("gm", "GM"),
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
    # Optional display alias — overrides the user's character identity in roster/thumbnails
    alias_type = models.CharField(
        max_length=20, choices=POSTED_AS_TYPE_CHOICES, blank=True, default="",
    )
    alias_name = models.CharField(max_length=200, blank=True, default="")
    alias_id = models.PositiveIntegerField(null=True, blank=True)
    hidden = models.BooleanField(
        default=False,
        help_text="Hidden members have read-only shadow access (from Gain Access cyber action).",
    )

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


CYBER_ACTION_CHOICES = [
    ("gain_access", "Gain Access"),
    ("deploy", "Deploy"),
    ("defend", "Defend"),
    ("detect", "Detect"),
]

THREAD_EFFECT_CHOICES = [
    ("encrypted", "Encrypted"),
    ("obfuscated", "Obfuscated"),
    ("backdoor", "Backdoor"),
    ("compromised", "Compromised"),
    ("locked", "Locked"),
]


class CyberAction(models.Model):
    """Log of a cyber terminal action performed on a thread."""

    thread = models.ForeignKey(
        Thread, on_delete=models.CASCADE, related_name="cyber_actions",
    )
    actor = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="cyber_actions",
    )
    # Persona used for the action
    actor_persona_type = models.CharField(max_length=20, blank=True, default="")
    actor_persona_id = models.PositiveIntegerField(null=True, blank=True)
    actor_persona_name = models.CharField(max_length=200, blank=True, default="")
    # Target (optional — specific user being targeted)
    target_user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="cyber_actions_against",
    )
    action_type = models.CharField(max_length=20, choices=CYBER_ACTION_CHOICES)
    dice_pool = models.PositiveIntegerField(default=0)
    dice_results = models.JSONField(
        default=list, help_text="List of individual d10 results.",
    )
    successes = models.IntegerField(default=0)
    is_exceptional = models.BooleanField(default=False)
    is_dramatic_failure = models.BooleanField(default=False)
    gm_modifier = models.IntegerField(
        default=0, help_text="Bonus (+) or penalty (-) dice from GM.",
    )
    notes = models.TextField(blank=True, default="")
    outcome = models.TextField(
        blank=True, default="",
        help_text="Description of what happened as a result.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.actor_persona_name or self.actor.username} → {self.action_type} ({self.successes} successes)"


class ThreadEffect(models.Model):
    """An active cyber effect on a thread."""

    thread = models.ForeignKey(
        Thread, on_delete=models.CASCADE, related_name="cyber_effects",
    )
    effect_type = models.CharField(max_length=20, choices=THREAD_EFFECT_CHOICES)
    level = models.PositiveIntegerField(
        default=1, help_text="Effect strength (1-3 for encryption).",
    )
    source_user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="created_effects",
    )
    source_agency_id = models.PositiveIntegerField(
        null=True, blank=True, help_text="Agency that placed this effect.",
    )
    target_agency_id = models.PositiveIntegerField(
        null=True, blank=True, help_text="Agency targeted by this effect.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.effect_type} (lvl {self.level}) on {self.thread}"
