from django.db import models
from django.contrib.auth.models import User


class NPC(models.Model):
    STATE_CHOICES = [
        ("active", "Active"),
        ("leave", "Leave"),
        ("medical_leave", "Medical Leave"),
        ("missing", "Missing"),
        ("deceased", "Deceased"),
    ]

    name = models.CharField(max_length=200)
    image = models.ImageField(upload_to="npc_portraits/", blank=True, null=True)
    age = models.IntegerField(blank=True, null=True)
    sex = models.CharField(max_length=50, blank=True, default="")
    pronouns = models.CharField(max_length=50, blank=True, default="")
    nationality = models.CharField(max_length=100, blank=True, default="")
    occupation = models.CharField(max_length=200, blank=True, default="")
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default="active")
    bio = models.TextField(blank=True, default="")
    assigned_to = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="assigned_npcs"
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="created_npcs"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.name} ({self.get_state_display()})"
