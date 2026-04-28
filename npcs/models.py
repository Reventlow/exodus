from django.db import models
from django.contrib.auth.models import User
from characters.models import default_attributes, default_skills


class NPC(models.Model):
    STATE_CHOICES = [
        ("active", "Active"),
        ("leave", "Leave"),
        ("medical_leave", "Medical Leave"),
        ("missing", "Missing"),
        ("compromised", "Compromised — Underground"),
        ("deceased", "Deceased"),
    ]

    CLASS_CHOICES = [
        ("fixer", "Fixer"),
        ("soldier", "Soldier"),
        ("science", "Science"),
        ("engineer", "Engineer"),
        ("ai", "AI"),
    ]

    name = models.CharField(max_length=200)
    character_class = models.CharField(
        max_length=20, choices=CLASS_CHOICES, blank=True, default=""
    )
    class_classified = models.BooleanField(
        default=False,
        help_text="If true, the class is shown as CLASSIFIED to non-superusers.",
    )
    image = models.ImageField(upload_to="npc_portraits/", blank=True, null=True)
    age = models.IntegerField(blank=True, null=True)
    sex = models.CharField(max_length=50, blank=True, default="")
    pronouns = models.CharField(max_length=50, blank=True, default="")
    nationality = models.CharField(max_length=100, blank=True, default="")
    occupation = models.CharField(max_length=200, blank=True, default="")
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default="active")
    detected_by_agency = models.CharField(
        max_length=200, blank=True, default="",
        help_text="Agency that detected this NPC during cyber operations. Set when compromised.",
    )
    bio = models.TextField(blank=True, default="")
    assigned_to = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="assigned_npcs",
        blank=True, null=True,
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="created_npcs"
    )

    # NPC dossier fields
    is_npc_dossier = models.BooleanField(
        default=False,
        help_text="NPC dossiers are admin-managed and linked to NPC agencies.",
    )
    agency = models.ForeignKey(
        "agencies.Agency", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="npc_dossiers",
        help_text="The NPC agency this dossier belongs to.",
    )
    is_hidden = models.BooleanField(
        default=False,
        help_text="Hidden dossiers are only visible to superusers.",
    )
    is_child_prodigy = models.BooleanField(
        default=False,
        help_text="Tagged as a child prodigy recruited via fringe science.",
    )

    # WoD 2.0 stats (superuser-only, mirrors Character model)
    attributes = models.JSONField(default=default_attributes)
    skills = models.JSONField(default=default_skills)
    health_bashing = models.IntegerField(default=0)
    health_lethal = models.IntegerField(default=0)
    health_aggravated = models.IntegerField(default=0)
    size = models.IntegerField(default=5)
    mental_load = models.IntegerField(default=0)
    willpower_current = models.IntegerField(default=0)
    experience = models.IntegerField(default=0)
    experience_used = models.IntegerField(default=0)
    merits_old = models.JSONField(default=list, db_column="merits")
    merit_entries = models.ManyToManyField(
        "exodus.MeritDefinition", through="NpcMerit", blank=True,
    )
    pulling_strings = models.ManyToManyField(
        "exodus.PullingString", through="NpcPullingString", blank=True,
    )
    flaws = models.JSONField(default=list)
    specialisations = models.JSONField(default=list)
    # v0.15.34 — per-session merit-use tracking (mirrors
    # Character.merit_uses). Keyed by merit name, value is the count of
    # uses spent this session. Drives the Gun Fu auto-success spend on
    # NPCs driven by the GM in combat (the NPC sheet otherwise has no
    # session-state tracking — every other merit is rating-only). Reset
    # via the same mechanism as characters (RESET MERIT USES on the
    # underlying sheet, or via an admin / API write).
    merit_uses = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        prefix = "[NPC] " if self.is_npc_dossier else ""
        return f"{prefix}{self.name} ({self.get_state_display()})"


class NpcMerit(models.Model):
    """Through table for NPC ↔ merit definition."""
    npc = models.ForeignKey(NPC, on_delete=models.CASCADE, related_name="npc_merits")
    merit = models.ForeignKey("exodus.MeritDefinition", on_delete=models.CASCADE)
    rating = models.IntegerField(default=1)

    class Meta:
        ordering = ["merit__category", "merit__name"]

    def __str__(self):
        return f"{self.npc.name}: {self.merit.name} ({self.rating})"


class NpcPullingString(models.Model):
    """Through table for NPC ↔ pulling string."""
    npc = models.ForeignKey(NPC, on_delete=models.CASCADE, related_name="npc_pulling_strings")
    pulling_string = models.ForeignKey("exodus.PullingString", on_delete=models.CASCADE)

    class Meta:
        ordering = ["pulling_string__category", "pulling_string__name"]

    def __str__(self):
        return f"{self.npc.name}: {self.pulling_string.name}"


class NPCNote(models.Model):
    """Player-submitted notes on NPC dossiers."""

    npc = models.ForeignKey(NPC, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="npc_notes")
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Note by {self.author.username} on {self.npc.name}"
