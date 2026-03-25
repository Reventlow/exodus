"""Core models for Exodus site configuration."""

from django.db import models


class PullingString(models.Model):
    """Game-level catalog of available pulling strings."""

    CATEGORY_CHOICES = [
        ("general", "General"),
        ("fixer", "Fixer"),
        ("soldier", "Soldier"),
        ("science", "Science"),
        ("engineer", "Engineer"),
        ("ai", "AI"),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    cost = models.IntegerField(default=0, help_text="XP cost to acquire.")
    category = models.CharField(
        max_length=20, choices=CATEGORY_CHOICES, default="general"
    )

    is_linkable = models.BooleanField(
        default=False,
        help_text="If true, each instance can be linked to an NPC dossier. Can be taken multiple times.",
    )

    class Meta:
        ordering = ["category", "name"]

    def __str__(self):
        return f"{self.name} ({self.get_category_display()}, {self.cost} XP)"


class MeritDefinition(models.Model):
    """Game-level catalog of available merits."""

    CATEGORY_CHOICES = [
        ("physical", "Physical"),
        ("mental", "Mental"),
        ("social", "Social"),
        ("supernatural", "Supernatural"),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    cost = models.IntegerField(
        default=1,
        help_text="Dot cost. For variable merits (e.g. 1-5), store the max rating.",
    )
    min_cost = models.IntegerField(
        default=1,
        help_text="Minimum dot rating. Set equal to cost for fixed-cost merits.",
    )
    category = models.CharField(
        max_length=20, choices=CATEGORY_CHOICES, default="physical"
    )
    prerequisites = models.CharField(
        max_length=200, blank=True, default="",
        help_text="Human-readable prerequisites (e.g. 'Stamina 4+').",
    )
    effects = models.JSONField(
        default=dict, blank=True,
        help_text=(
            "Mechanical effects as JSON. Keys: "
            "extra_health (int), size_mod (int), "
            "stat_bonus ({stat: bonus}), "
            "skill_bonus ({skill: bonus}), "
            "difficulty_mod ({context: mod}), "
            "willpower_mod (int), speed_mod (int), "
            "custom (str description of non-standard effect)."
        ),
    )

    class Meta:
        ordering = ["category", "name"]

    def __str__(self):
        if self.min_cost == self.cost:
            return f"{self.name} ({self.get_category_display()}, {self.cost} dots)"
        return f"{self.name} ({self.get_category_display()}, {self.min_cost}-{self.cost} dots)"


class SiteSettings(models.Model):
    """Singleton model for site-wide settings."""

    next_game_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date of the next game session.",
    )
    charter_text = models.TextField(
        blank=True,
        default="",
        help_text="United Interstellar Council charter content (Markdown).",
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
