from django.db import models
from django.contrib.auth.models import User


def default_alliance():
    """Default alliance structure with three member categories."""
    return {"countries": [], "companies": [], "organizations": []}


def default_agency_attributes():
    """Default agency attribute structure. All start at 0."""
    return {
        "power": {"Industry": 0, "Science": 0, "Military": 0, "Agriculture": 0},
        "finesse": {"Espionage": 0, "Diplomacy": 0, "Logistics": 0, "Trade": 0},
        "resistance": {
            "Unity": 0,
            "Surveillance": 0,
            "Ethics": 0,
            "Counter Espionage": 0,
            "Security": 0,
        },
    }


class Agency(models.Model):
    # Identity
    name = models.CharField(max_length=200)
    alliance = models.JSONField(default=default_alliance)  # {countries:[], companies:[], organizations:[]}
    motto = models.CharField(max_length=200, blank=True, default="")
    headquarters = models.CharField(max_length=200, blank=True, default="")
    notes = models.TextField(blank=True, default="")

    # Core stats (unbounded integers, can go negative)
    integrity = models.IntegerField(default=0)
    experience = models.IntegerField(default=0)

    # Agency type
    is_player_agency = models.BooleanField(default=False)

    # United Interstellar Council membership
    is_council_member = models.BooleanField(default=False)
    is_council_chairman = models.BooleanField(default=False)

    # Attributes: {power: {Industry: 3, ...}, finesse: {...}, resistance: {...}}
    attributes = models.JSONField(default=default_agency_attributes)

    # List sections stored as JSON arrays
    specializations = models.JSONField(default=list)  # [{name, relatedSkill, effect}]
    merits = models.JSONField(default=list)  # [{name, value, description}]
    flaws = models.JSONField(default=list)  # [{name, value, description}]
    assets = models.JSONField(default=list)  # [{name, type, status, notes}]
    fleet = models.JSONField(default=list)  # [{shipClass, role, quantity, notes}]
    conditions = models.JSONField(default=list)  # [{condition, source, effect, duration}]
    projects = models.JSONField(default=list)  # [{name, player, duration, completionScore, notes}]
    history = models.JSONField(default=list)  # [{year, decision, consequence}]

    # NPC visibility: {fieldPath: bool} — true = visible, false = classified
    field_visibility = models.JSONField(default=dict)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_player_agency", "name"]
        verbose_name_plural = "agencies"

    def __str__(self):
        tag = "[PLAYER]" if self.is_player_agency else "[NPC]"
        return f"{tag} {self.name}"


class ChangeRequest(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    agency = models.ForeignKey(
        Agency, on_delete=models.CASCADE, related_name="change_requests"
    )
    requester = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="agency_change_requests"
    )
    field_name = models.CharField(max_length=100)
    description = models.TextField()
    proposed_changes = models.JSONField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    admin_note = models.TextField(blank=True, default="")
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_change_requests",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.field_name} change by {self.requester.username} ({self.status})"


class GlobalFlaw(models.Model):
    """A flaw that applies to ALL agencies globally.

    Managed by superusers via the global flaws management page.
    Appears on every agency sheet alongside agency-specific flaws,
    but visually distinguished and not editable from the agency sheet.
    """

    name = models.CharField(max_length=200)
    value = models.IntegerField(default=0)
    description = models.TextField(blank=True, default="")
    order = models.IntegerField(default=0, help_text="Lower numbers appear first.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return f"[GLOBAL] {self.name} ({self.value})"


class FTLProject(models.Model):
    """A global FTL (Faster Than Light) travel project definition.

    Managed by superadmins via the FTL projects management page.
    Can be assigned to individual agencies to track per-agency progress.
    """

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    pros = models.JSONField(default=list)  # [{text: "..."}]
    cons = models.JSONField(default=list)  # [{text: "..."}]
    required_successes = models.IntegerField(default=10)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"[FTL] {self.name}"


class AgencyFTLProject(models.Model):
    """Join table tracking per-agency progress on an FTL project.

    Links an Agency to an FTLProject with a progress counter
    (current_successes toward the project's required_successes).
    """

    agency = models.ForeignKey(
        Agency, on_delete=models.CASCADE, related_name="ftl_assignments"
    )
    ftl_project = models.ForeignKey(
        FTLProject, on_delete=models.CASCADE, related_name="agency_assignments"
    )
    current_successes = models.IntegerField(default=0)
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["agency", "ftl_project"]

    def __str__(self):
        return f"{self.agency.name} — {self.ftl_project.name} ({self.current_successes})"


class CouncilItem(models.Model):
    """An item from the United Interstellar Council.

    Council items represent agreements, common goal initiatives, or laws
    established by the council. Managed by superadmins, visible on all
    agency sheets as read-only.
    """

    ITEM_TYPE_CHOICES = [
        ("agreement", "Agreement"),
        ("initiative", "Initiative"),
        ("law", "Law"),
    ]

    STATUS_CHOICES = [
        ("proposed", "Proposed"),
        ("voting", "Voting"),
        ("active", "Active"),
        ("suspended", "Suspended"),
        ("repealed", "Repealed"),
    ]

    name = models.CharField(max_length=200)
    item_type = models.CharField(
        max_length=20, choices=ITEM_TYPE_CHOICES, default="agreement"
    )
    description = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="proposed")
    proposed_by = models.CharField(
        max_length=200, blank=True, default="",
        help_text="Name of the agency or entity that proposed this item.",
    )
    notes = models.TextField(blank=True, default="")
    order = models.IntegerField(default=0, help_text="Lower numbers appear first.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return f"[COUNCIL/{self.item_type.upper()}] {self.name} ({self.status})"
