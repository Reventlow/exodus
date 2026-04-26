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
    last_activity = models.DateTimeField(
        null=True, blank=True, db_index=True,
        help_text=(
            "Most recent authenticated HTTP request from this user. "
            "Updated by LastActivityMiddleware, debounced to once per 30s "
            "to limit DB writes. Used for activity monitoring; not exposed "
            "to other players."
        ),
    )

    def __str__(self) -> str:
        return f"Profile: {self.user.username}"
