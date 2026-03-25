from django.db import models
from django.contrib.auth.models import User


def default_attributes():
    """Default WoD 2.0 attribute structure. All start at 1."""
    return {
        "power": {"mental": 1, "physical": 1, "social": 1},
        "finesse": {"mental": 1, "physical": 1, "social": 1},
        "resistance": {"mental": 1, "physical": 1, "social": 1},
    }


def default_skills():
    """Default WoD 2.0 skill structure. All start at 0."""
    return {
        "mental": {
            "Academics": 0,
            "Computer": 0,
            "Crafts": 0,
            "Investigation": 0,
            "Medicine": 0,
            "Occult": 0,
            "Politics": 0,
            "Science": 0,
        },
        "physical": {
            "Athletics": 0,
            "Brawl": 0,
            "Drive": 0,
            "Firearms": 0,
            "Larceny": 0,
            "Stealth": 0,
            "Survival": 0,
            "Weaponry": 0,
        },
        "social": {
            "AnimalKen": 0,
            "Empathy": 0,
            "Expression": 0,
            "Intimidation": 0,
            "Persuasion": 0,
            "Socialize": 0,
            "Streetwise": 0,
            "Subterfuge": 0,
        },
    }


class Character(models.Model):
    CLASS_CHOICES = [
        ("fixer", "Fixer"),
        ("soldier", "Soldier"),
        ("science", "Science"),
        ("engineer", "Engineer"),
        ("ai", "AI"),
    ]

    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="characters"
    )

    # Info
    name = models.CharField(max_length=200, default="UNKNOWN AGENT")
    character_class = models.CharField(
        max_length=20, choices=CLASS_CHOICES, blank=True, default=""
    )
    concept = models.CharField(max_length=200, blank=True, default="")
    chronicle = models.CharField(max_length=200, blank=True, default="")
    virtue = models.CharField(max_length=100, blank=True, default="")
    vice = models.CharField(max_length=100, blank=True, default="")
    dossier = models.TextField(blank=True, default="")
    profile_picture = models.ImageField(
        upload_to="character_portraits/", blank=True, null=True
    )

    # Attributes stored as JSON: {power: {mental, physical, social}, finesse: {...}, resistance: {...}}
    attributes = models.JSONField(default=default_attributes)

    # Skills stored as JSON: {mental: {Academics: 0, ...}, physical: {...}, social: {...}}
    skills = models.JSONField(default=default_skills)

    # Health tracking
    health_bashing = models.IntegerField(default=0)
    health_lethal = models.IntegerField(default=0)
    health_aggravated = models.IntegerField(default=0)

    # Derived (only size is user-editable, rest calculated in frontend)
    size = models.IntegerField(default=5)

    # Lists as JSON arrays
    merits = models.JSONField(default=list)
    flaws = models.JSONField(default=list)
    pulling_strings = models.ManyToManyField(
        "exodus.PullingString", through="CharacterPullingString", blank=True,
    )
    inventory = models.JSONField(default=list)
    specialisations = models.JSONField(default=list)  # [{skill, name}]

    # Experience
    experience = models.IntegerField(default=0)
    experience_used = models.IntegerField(default=0)

    # Mental load (0-6, biosign stress indicator)
    mental_load = models.IntegerField(default=0)

    # Willpower tracking
    willpower_current = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.name} ({self.owner.username})"


class CharacterPullingString(models.Model):
    """Through table for character ↔ pulling string, with optional NPC link."""

    character = models.ForeignKey(
        Character, on_delete=models.CASCADE, related_name="character_pulling_strings"
    )
    pulling_string = models.ForeignKey(
        "exodus.PullingString", on_delete=models.CASCADE
    )
    linked_npc = models.ForeignKey(
        "npcs.NPC", on_delete=models.SET_NULL, null=True, blank=True,
        help_text="Linked NPC dossier (for linkable pulling strings like Personal NPC).",
    )

    class Meta:
        ordering = ["pulling_string__category", "pulling_string__name"]

    def __str__(self):
        npc = f" → {self.linked_npc.name}" if self.linked_npc else ""
        return f"{self.character.name}: {self.pulling_string.name}{npc}"
