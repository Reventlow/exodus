"""Core models for Exodus site configuration."""

from django.db import models


class SiteSettings(models.Model):
    """Singleton model for site-wide settings."""

    next_game_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date of the next game session.",
    )

    class Meta:
        verbose_name = "Site Settings"
        verbose_name_plural = "Site Settings"

    def __str__(self):
        return "Site Settings"

    def save(self, *args, **kwargs):
        """Enforce singleton: always use pk=1."""
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Prevent deletion of the singleton."""
        pass

    @classmethod
    def load(cls):
        """Load or create the singleton instance."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
