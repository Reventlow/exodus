"""Models for the accounts application."""

from django.contrib.auth.models import User
from django.db import models


class UserProfile(models.Model):
    """Extended profile for a user, storing avatar and other settings."""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="profile",
    )
    avatar = models.ImageField(
        upload_to="avatars/", blank=True, null=True,
        help_text="User avatar displayed in comms and profile.",
    )

    def __str__(self) -> str:
        return f"Profile: {self.user.username}"
