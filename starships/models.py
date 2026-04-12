"""Models for the starships application.

Two-tier design: a StarshipClass is a reusable blueprint that an agency
designs once, and a Starship is an instance (a physical hull) built
from that class and assigned to a Fleet. Modules come from a real
ShipModule table (not a JSON catalogue like BaseConfig) so they can be
queried, reordered, and edited without database blob rewrites.

Release A ships the schema and seed data only. Subsequent releases add
the settings catalogue UI (B), class editor (C), instance build flow
(D), fleet UI (E), star map overlay (F), and legacy fleet import (G).
"""

from django.db import models


# ---------------------------------------------------------------------------
# Catalogue (GM-editable)
# ---------------------------------------------------------------------------

class ShipType(models.Model):
    """Hull category — drone, shuttle, cruiser, carrier, dreadnaught, etc.

    Drives the default slot budget and baseline requirements before any
    module is added to a class. Size bounds constrain how small/large a
    class can declare its hull.
    """

    key = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")
    default_slot_budget = models.IntegerField(
        default=4,
        help_text="Module slots available before size/module adjustments.",
    )
    min_size = models.IntegerField(default=1)
    max_size = models.IntegerField(default=10)
    base_crew = models.IntegerField(default=0)
    base_energy = models.IntegerField(default=0)
    base_maintenance = models.IntegerField(default=0)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class ShipModuleSection(models.Model):
    """A tiered family of ship modules (e.g. Fighter Guns L1–L5).

    Sections enforce one-module-per-class: installing a level-3
    Gatling Gun into a class that already has a level-1 Single Auto
    Cannon atomically replaces the old one. Levels are fixed at 1-5.
    """

    key = models.CharField(max_length=60, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class ShipModule(models.Model):
    """A single module that can be installed in a starship class.

    Declares its slot cost plus deltas on crew/energy/maintenance so the
    class editor can compute totals live. Restrictions let catalogue
    authors scope modules to specific ship types (e.g. carrier-only
    drone bays).
    """

    CATEGORY_CHOICES = [
        ("propulsion", "Propulsion"),
        ("power", "Power"),
        ("weapons", "Weapons"),
        ("defense", "Defense"),
        ("sensors", "Sensors"),
        ("quarters", "Crew Quarters"),
        ("cargo", "Cargo"),
        ("hangar", "Hangar / Bay"),
        ("command", "Command & Control"),
        ("special", "Special"),
    ]

    key = models.CharField(max_length=60, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    category = models.CharField(
        max_length=20, choices=CATEGORY_CHOICES, default="special",
    )
    slot_cost = models.IntegerField(default=1)
    crew_delta = models.IntegerField(
        default=0,
        help_text="Change to required crew. Negative = automated module.",
    )
    energy_delta = models.IntegerField(default=0)
    maintenance_delta = models.IntegerField(default=0)
    provides_sublight = models.BooleanField(
        default=False,
        help_text="Class needs at least one module with this flag to manoeuvre.",
    )
    provides_ftl = models.BooleanField(
        default=False,
        help_text="Class needs this for interstellar travel.",
    )
    min_hull_size = models.IntegerField(
        default=1,
        help_text="Smallest hull that can fit this module.",
    )
    restricted_to_types = models.JSONField(
        default=list, blank=True,
        help_text="List of ShipType.key values; empty = available to all.",
    )
    build_cost_xp_delta = models.IntegerField(
        default=0,
        help_text="XP this module adds to the class's build cost.",
    )
    xp_cost = models.IntegerField(
        default=0,
        help_text="Research/unlock cost for this module (one-off).",
    )
    # Tiered family grouping — sectioned modules are mutually exclusive
    # within a class (installing one replaces the current level).
    section = models.ForeignKey(
        ShipModuleSection,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="modules",
        help_text="Optional tier family. Null = standalone module.",
    )
    level = models.IntegerField(
        default=0,
        help_text="Tier within the section (1-5). Ignored when section is null.",
    )
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ["category", "order", "name"]

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"


# ---------------------------------------------------------------------------
# Class (template)
# ---------------------------------------------------------------------------

class StarshipClass(models.Model):
    """A designed ship blueprint. One class → many Starship instances.

    Per-agency by default; GM-shared classes have created_by = null so
    every agency can build them. Build cost and required successes
    govern how expensive and how slow a single hull is to commission
    (mirrors FTL projects' progress roll mechanic).
    """

    name = models.CharField(max_length=200)
    ship_type = models.ForeignKey(
        ShipType, on_delete=models.PROTECT, related_name="classes",
    )
    size = models.IntegerField(
        default=1,
        help_text="Hull size. Must fall within the ShipType's min/max.",
    )
    description = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        "agencies.Agency",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="starship_classes",
        help_text="Null = GM-shared class available to all agencies.",
    )
    is_locked = models.BooleanField(
        default=False,
        help_text="Locked classes cannot be edited; used once a design is finalised.",
    )
    build_cost_xp = models.IntegerField(
        default=0,
        help_text="XP cost to commission one hull of this class.",
    )
    build_required_successes = models.IntegerField(
        default=5,
        help_text="Successes needed on construction rolls (like FTL projects).",
    )
    modules = models.ManyToManyField(
        ShipModule,
        through="ClassModule",
        related_name="classes",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "starship classes"

    def __str__(self):
        owner = self.created_by.name if self.created_by else "shared"
        return f"{self.name} ({self.ship_type.name}, {owner})"


class ClassModule(models.Model):
    """Through-table binding a module to a class with quantity/notes."""

    starship_class = models.ForeignKey(
        StarshipClass, on_delete=models.CASCADE, related_name="class_modules",
    )
    module = models.ForeignKey(
        ShipModule, on_delete=models.PROTECT, related_name="class_installs",
    )
    quantity = models.IntegerField(default=1)
    notes = models.TextField(blank=True, default="")
    position = models.IntegerField(
        default=0,
        help_text="Render order in the class editor.",
    )

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return f"{self.quantity}x {self.module.name} @ {self.starship_class.name}"


# ---------------------------------------------------------------------------
# Instance (physical hull)
# ---------------------------------------------------------------------------

class Fleet(models.Model):
    """A grouping of starships under a commander, owned by an agency."""

    name = models.CharField(max_length=200)
    agency = models.ForeignKey(
        "agencies.Agency", on_delete=models.CASCADE, related_name="fleets",
    )
    commander = models.CharField(
        max_length=200, blank=True, default="",
        help_text="Character name commanding this fleet.",
    )
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["agency", "name"]

    def __str__(self):
        return f"{self.name} ({self.agency.name})"


class Starship(models.Model):
    """A physical hull built from a StarshipClass blueprint.

    Construction uses the same progress-roll model as FTL projects:
    under_construction hulls accumulate current_successes until they
    hit the class's build_required_successes, then auto-promote to
    active. Location is a FK → StarSystem so the star map overlay can
    draw ship icons in later releases.
    """

    STATUS_CHOICES = [
        ("under_construction", "Under Construction"),
        ("active", "Active"),
        ("damaged", "Damaged"),
        ("in_dock", "In Dock"),
        ("decommissioned", "Decommissioned"),
        ("lost", "Lost"),
    ]

    name = models.CharField(max_length=200)
    hull_number = models.CharField(max_length=50, blank=True, default="")
    starship_class = models.ForeignKey(
        StarshipClass, on_delete=models.PROTECT, related_name="hulls",
    )
    agency = models.ForeignKey(
        "agencies.Agency", on_delete=models.CASCADE, related_name="starships",
    )
    fleet = models.ForeignKey(
        Fleet, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="ships",
    )
    status = models.CharField(
        max_length=30, choices=STATUS_CHOICES, default="under_construction",
    )
    current_crew = models.IntegerField(
        default=0, help_text="Filled crew slots; compare vs class required_crew.",
    )
    maintenance_state = models.IntegerField(
        default=100,
        help_text="Percentage. 0 = wreck, 100 = pristine.",
    )
    # Construction progress — only meaningful while status=under_construction.
    current_successes = models.IntegerField(default=0)
    build_assigned_base = models.ForeignKey(
        "agencies.Base",
        on_delete=models.SET_NULL,
        null=True, blank=True, related_name="building_ships",
        help_text="Shipyard/base currently constructing this hull.",
    )
    # Location — used by the star map overlay.
    location = models.ForeignKey(
        "starmap.StarSystem",
        on_delete=models.SET_NULL,
        null=True, blank=True, related_name="docked_ships",
    )
    commissioned_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["agency", "name"]

    def __str__(self):
        return f"{self.name} ({self.starship_class.name})"
