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
    is_council_present = models.BooleanField(default=False)

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
        ("emergency_suspended", "Emergency Suspended"),
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
    vote_record = models.JSONField(
        default=dict, blank=True,
        help_text="Frozen vote snapshot when vote concludes or is emergency suspended.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return f"[COUNCIL/{self.item_type.upper()}] {self.name} ({self.status})"


class CouncilVote(models.Model):
    """A vote cast by a member agency on a council item."""

    VOTE_CHOICES = [
        ("for", "For"),
        ("against", "Against"),
        ("abstain", "Abstain"),
    ]

    council_item = models.ForeignKey(
        CouncilItem, on_delete=models.CASCADE, related_name="votes"
    )
    agency = models.ForeignKey(
        Agency, on_delete=models.CASCADE, related_name="council_votes"
    )
    vote = models.CharField(max_length=10, choices=VOTE_CHOICES)
    voted_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["council_item", "agency"]

    def __str__(self):
        return f"{self.agency.name} — {self.vote} on {self.council_item.name}"


def default_base_location_types():
    """Default location types with exp costs and space."""
    return [
        {
            "key": "official_building",
            "name": "Official Building",
            "exp": 5,
            "space": 20,
            "description": "An official government building.",
            "included": "",
        },
        {
            "key": "estate",
            "name": "Estate",
            "exp": 5,
            "space": 14,
            "description": "A luxury place, built for the good life style.",
            "included": "Built-in gym, pool, four car garage and 10 high-end bedrooms at no extra cost.",
        },
        {
            "key": "military_base",
            "name": "Military Base",
            "exp": 15,
            "space": 30,
            "description": "A full military installation.",
            "included": "Includes barracks, armory, brig, and shooting range at no extra cost.",
        },
        {
            "key": "black_site",
            "name": "Black Site",
            "exp": 7,
            "space": 8,
            "description": "A small secret base.",
            "included": "Includes armory, medical room and barracks for 12 people.",
        },
    ]


def default_base_location_merits():
    """Default location merits with exp costs and optional space bonuses."""
    return [
        {
            "key": "armored",
            "name": "Armored Building",
            "exp": 5,
            "extraSpace": 0,
            "description": "Armored to withstand outside assault. Has external checkpoints and built with security in mind.",
        },
        {
            "key": "underwater",
            "name": "Underwater",
            "exp": 10,
            "extraSpace": 0,
            "description": "The base is built under water.",
        },
        {
            "key": "underground",
            "name": "Underground",
            "exp": 15,
            "extraSpace": 0,
            "description": "A covert constructed underground base.",
        },
        {
            "key": "extra_large",
            "name": "Extra Large",
            "exp": 10,
            "extraSpace": 10,
            "description": "Grants extra 10 space.",
        },
        {
            "key": "super_large",
            "name": "Super Large",
            "exp": 20,
            "extraSpace": 20,
            "description": "Grants extra 20 space.",
        },
        {
            "key": "front",
            "name": "Front",
            "exp": 7,
            "extraSpace": 0,
            "description": "The location disguises as a front for something else.",
        },
    ]


def default_base_facility_types():
    """Default facility types with levels, exp costs, and sizes."""
    return [
        {
            "key": "aviation",
            "name": "Aviation Facility",
            "levels": [
                {"level": 1, "name": "Airstrip", "exp": 6, "size": 8, "description": "An airstrip with control tower and hangars."},
                {"level": 2, "name": "Airstrip + Helipad", "exp": 7, "size": 10, "description": "Includes level 1 and also houses a fleet of choppers."},
                {"level": 3, "name": "Space Launch Pad", "exp": 16, "size": 20, "description": "Full space launch capability."},
            ],
        },
        {
            "key": "auditorium",
            "name": "High Tech Auditorium",
            "levels": [
                {"level": 1, "name": "Auditorium", "exp": 3, "size": 1, "description": "A high tech auditorium with the entire works."},
            ],
        },
        {
            "key": "barracks",
            "name": "Barracks",
            "levels": [
                {"level": 1, "name": "Standard", "exp": 2, "size": 3, "description": "Standard soldiers and military police."},
                {"level": 2, "name": "Special Forces", "exp": 4, "size": 5, "description": "Includes level 1 and low-tier special forces."},
                {"level": 3, "name": "Elite Forces", "exp": 8, "size": 6, "description": "Includes level 1-2 and top-tier special forces."},
                {"level": 4, "name": "Black Ops", "exp": 16, "size": 7, "description": "Includes level 1-3 and off-the-books units."},
            ],
        },
        {
            "key": "armory",
            "name": "Armory",
            "levels": [
                {"level": 1, "name": "Small Arms", "exp": 2, "size": 1, "description": "Small arms and infantry weapons."},
                {"level": 2, "name": "Vehicle Ordnance", "exp": 4, "size": 3, "description": "Includes level 1 and weapons ordnance for tanks and transport vehicles."},
                {"level": 3, "name": "Tactical Ordnance", "exp": 6, "size": 5, "description": "Includes level 1-2 and ordnance for fighter planes, bombers, small/medium vessels and drones."},
                {"level": 4, "name": "Long Range", "exp": 10, "size": 8, "description": "Includes level 1-3 and weapons ordnance for long range tactical vessels."},
                {"level": 5, "name": "WMD (Short/Med)", "exp": 12, "size": 10, "description": "Includes level 1-4 and short + medium weapons of mass destruction."},
                {"level": 6, "name": "ICBM + Rail Guns", "exp": 20, "size": 16, "description": "Includes level 1-5 and intercontinental weapons and rail guns."},
            ],
        },
        {
            "key": "brig",
            "name": "Brig",
            "levels": [
                {"level": 1, "name": "Standard Detention", "exp": 1, "size": 3, "description": "Standard detention center."},
                {"level": 2, "name": "Max Security", "exp": 2, "size": 4, "description": "Includes level 1 and max security detention."},
                {"level": 3, "name": "Black Site Detention", "exp": 4, "size": 5, "description": "Includes level 1-2 and black site detention."},
                {"level": 4, "name": "Environmental Enclosed", "exp": 8, "size": 8, "description": "Includes level 1-3 and environmental enclosed detention with custom life support."},
            ],
        },
        {
            "key": "medical",
            "name": "Medical",
            "levels": [
                {"level": 1, "name": "Field Hospital", "exp": 2, "size": 2, "description": "Field hospital with staff."},
                {"level": 2, "name": "Medical Hospital", "exp": 8, "size": 5, "description": "Full medical hospital with staff."},
                {"level": 3, "name": "Intensive Care Unit", "exp": 10, "size": 2, "description": "Closed ICU with life support, medical, security, engineering and science staff."},
            ],
        },
        {
            "key": "computer_core",
            "name": "Computer Core",
            "levels": [
                {"level": 1, "name": "Small Data Center", "exp": 4, "size": 1, "description": "Small data center."},
                {"level": 2, "name": "Huge Data Center", "exp": 8, "size": 12, "description": "Huge data center."},
                {"level": 3, "name": "Quantum Super Server", "exp": 14, "size": 3, "description": "Quantum super server."},
            ],
        },
        {
            "key": "storage",
            "name": "Storage Area",
            "levels": [
                {"level": 1, "name": "Small Storage", "exp": 1, "size": 1, "description": "Small storage area."},
                {"level": 2, "name": "Large Storage", "exp": 3, "size": 8, "description": "Large storage area."},
                {"level": 3, "name": "Huge Storage", "exp": 8, "size": 16, "description": "Huge storage area."},
            ],
        },
        {
            "key": "workspace",
            "name": "Workspace",
            "levels": [
                {"level": 1, "name": "Normal", "exp": 0, "size": 1, "description": "Normal workspace."},
                {"level": 2, "name": "Good (+1)", "exp": 1, "size": 1, "description": "Good workspace (+1 to rolls)."},
                {"level": 3, "name": "Excellent (+3)", "exp": 5, "size": 1, "description": "Excellent workspace (+3 to rolls)."},
                {"level": 4, "name": "Superb (+5)", "exp": 10, "size": 1, "description": "Superb workspace (+5 to rolls)."},
            ],
        },
        {
            "key": "hr_offboarding",
            "name": "HR Off-boarding Office Suite 55",
            "levels": [
                {"level": 1, "name": "Suite 55", "exp": 5, "size": 2, "description": "HR off-boarding office suite 55."},
            ],
        },
    ]


def default_base_equipment_types():
    """Default facility equipment types with exp costs and requirements."""
    return [
        {
            "key": "short_med_planes",
            "name": "Short & Medium Range Planes",
            "exp": 4,
            "category": "Aviation Units",
            "requires": "Requires aviation facility and armory.",
        },
        {
            "key": "helicopters",
            "name": "Short & Medium Range Helicopters",
            "exp": 2,
            "category": "Aviation Units",
            "requires": "Requires aviation facility and armory.",
        },
        {
            "key": "long_range_planes",
            "name": "Long Range Planes",
            "exp": 8,
            "category": "Aviation Units",
            "requires": "Requires aviation facility and armory.",
        },
        {
            "key": "orbital_vehicles",
            "name": "Orbital Vehicles",
            "exp": 14,
            "category": "Aviation Units",
            "requires": "Requires aviation facility and armory.",
        },
        {
            "key": "internal_security",
            "name": "Internal Security & Checkpoint",
            "exp": 1,
            "category": "Base Defenses",
            "requires": "",
        },
        {
            "key": "segmented_security",
            "name": "Segmented Security Levels",
            "exp": 4,
            "category": "Base Defenses",
            "requires": "",
        },
        {
            "key": "high_level_monitoring",
            "name": "High Level Monitoring",
            "exp": 8,
            "category": "Base Defenses",
            "requires": "",
        },
        {
            "key": "external_defense",
            "name": "External Defense (Phalanx / Short Range Radar)",
            "exp": 3,
            "category": "Base Defenses",
            "requires": "",
        },
        {
            "key": "sam_ssm",
            "name": "SAM & SSM Defense (Medium/Long Range)",
            "exp": 6,
            "category": "Base Defenses",
            "requires": "",
        },
    ]


class BaseConfig(models.Model):
    """Singleton configuration for base locations, merits, facilities, and equipment.

    Stores all predefined options with their exp costs and sizes.
    Editable by superusers via the base config settings page.
    """

    location_types = models.JSONField(default=default_base_location_types)
    location_merits = models.JSONField(default=default_base_location_merits)
    facility_types = models.JSONField(default=default_base_facility_types)
    equipment_types = models.JSONField(default=default_base_equipment_types)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Base Configuration"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return "Base Configuration"

    @classmethod
    def load(cls):
        """Load or create the singleton config instance."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Base(models.Model):
    """A base/installation belonging to an agency.

    Stores selections by key. Costs and sizes are computed from
    the BaseConfig singleton at display time.
    """

    agency = models.ForeignKey(
        Agency, on_delete=models.CASCADE, related_name="bases"
    )
    name = models.CharField(max_length=200, default="NEW BASE")
    location_type = models.CharField(max_length=100, blank=True, default="")
    merits = models.JSONField(default=list)  # [merit_key, ...]
    facilities = models.JSONField(default=list)  # [{key, level}]
    workspaces = models.JSONField(default=list)  # [{level, assignedTo, assignedType}]
    equipment = models.JSONField(default=list)  # [equipment_key, ...]
    notes = models.TextField(blank=True, default="")
    is_hidden = models.BooleanField(
        default=False,
        help_text="Hidden bases are only visible to superusers.",
    )
    hidden_sections = models.JSONField(
        default=list,
        help_text="List of section keys hidden from non-superusers (e.g. facilities, equipment).",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.agency.name})"
