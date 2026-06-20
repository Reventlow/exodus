"""Models for the starmap application."""

from django.db import models


class StarSystem(models.Model):
    """A star system on the 3D star map."""

    name = models.CharField(max_length=200, unique=True)
    x = models.FloatField(help_text="3D x-coordinate in light-years, Sol at origin.")
    y = models.FloatField(help_text="3D y-coordinate in light-years.")
    z = models.FloatField(help_text="3D z-coordinate in light-years.")
    distance = models.FloatField(help_text="Distance from Sol in light-years.")
    spectral_type = models.CharField(max_length=20)
    planets = models.IntegerField(default=0)
    is_sol = models.BooleanField(default=False)
    is_endgame = models.BooleanField(
        default=False,
        help_text="Visible but unreachable beacon system.",
    )

    # Ground truth resources — only GM sees these directly
    resources = models.JSONField(
        default=dict,
        help_text='{"ice": 0-100, "metals": ..., "rareEarth": ..., "helium3": ..., "hydrocarbons": ..., "exotic": ...}',
    )
    scan_level_truth = models.IntegerField(
        default=0,
        help_text="Vestigial (legacy scan-level system). Superseded by the uncertainty model.",
    )
    # --- Star-intel scanning system (single source of truth) ---
    discovered = models.BooleanField(
        default=False,
        help_text="GM gate: a system must be discovered before agencies can scan or retrieve data.",
    )
    has_livable_planet = models.BooleanField(
        default=False,
        help_text="Single truth: does this system have a livable planet? Scanning approximates it.",
    )
    difficulty_mod = models.IntegerField(
        default=0,
        help_text="Scan difficulty modifier -10..+10. Target successes = 15 + this (clamped 5..25).",
    )

    # Claim
    claimed_by = models.ForeignKey(
        "agencies.Agency",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="claimed_systems",
    )
    claimed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["distance", "name"]

    def __str__(self):
        return f"{self.name} ({self.spectral_type}, {self.distance:.1f} ly)"


class AgencyScan(models.Model):
    """Per-agency scan data for a star system. Exclusive and tradeable."""

    agency = models.ForeignKey(
        "agencies.Agency",
        on_delete=models.CASCADE,
        related_name="star_scans",
    )
    star_system = models.ForeignKey(
        StarSystem,
        on_delete=models.CASCADE,
        related_name="agency_scans",
    )
    scan_level = models.IntegerField(
        default=0,
        help_text="0=none, 1=survey, 2=focused, 3=deep.",
    )
    scanned_resources = models.JSONField(
        default=dict,
        help_text="Resources with uncertainty applied based on scan level.",
    )
    current_successes = models.IntegerField(
        default=0,
        help_text="Accumulated successes toward next scan level.",
    )
    required_successes = models.IntegerField(
        default=3,
        help_text="Successes needed for next level (3/5/8).",
    )

    # Assignment (mirrors AgencyFTLProject)
    player = models.CharField(max_length=200, blank=True, default="")
    base_id = models.IntegerField(null=True, blank=True)
    base_name = models.CharField(max_length=200, blank=True, default="")
    metadata = models.JSONField(default=dict)

    scanned_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["agency", "star_system"]
        ordering = ["-scanned_at"]

    def __str__(self):
        return f"{self.agency.name} scan of {self.star_system.name} (level {self.scan_level})"


class ScanRollLog(models.Model):
    """Log of a scan roll on a star system."""

    agency = models.ForeignKey(
        "agencies.Agency",
        on_delete=models.CASCADE,
        related_name="scan_roll_logs",
    )
    scan = models.ForeignKey(
        AgencyScan,
        on_delete=models.CASCADE,
        related_name="roll_logs",
    )
    star_system_name = models.CharField(max_length=200)
    character_name = models.CharField(max_length=200)
    roll_type = models.CharField(max_length=20)
    pool = models.IntegerField()
    rolls = models.JSONField(default=list)
    successes = models.IntegerField(default=0)
    old_level = models.IntegerField(default=0)
    new_level = models.IntegerField(default=0)
    message = models.TextField(blank=True, default="")
    rolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-rolled_at"]

    def __str__(self):
        return f"{self.character_name} — scan {self.star_system_name} ({self.successes}s)"


class ResourceType(models.Model):
    """GM-defined resource type for star systems."""

    key = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=20, default="#00ff88")
    icon = models.CharField(max_length=10, blank=True, default="")
    order = models.IntegerField(default=0)

    # Absolute-quantity model. Values on StarSystem.resources are integers in
    # these units, not percentages. Brackets below define scan uncertainty
    # in the same unit.
    unit_label = models.CharField(
        max_length=50, default="units",
        help_text="Gameplay unit, e.g. 'carrier loads', 'kt ore', 'canisters'.",
    )
    unit_description = models.CharField(
        max_length=200, blank=True, default="",
        help_text="Human-readable meaning of one unit, e.g. '1 load = one drone carrier refuel'.",
    )
    typical_min = models.IntegerField(
        default=0,
        help_text="Galaxy-wide low end used by the procedural seeder.",
    )
    typical_max = models.IntegerField(
        default=100,
        help_text="Galaxy-wide high end used by the procedural seeder.",
    )
    rarity_weight = models.FloatField(
        default=1.0,
        help_text="0.0-1.0 probability this resource is present in a given system.",
    )
    scan_bracket_wide = models.IntegerField(
        default=40,
        help_text="+/- uncertainty in units at scan level 1 (survey).",
    )
    scan_bracket_narrow = models.IntegerField(
        default=15,
        help_text="+/- uncertainty in units at scan level 2 (focused). Level 3 is exact.",
    )

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class Civilisation(models.Model):
    """A species or civilisation that can inhabit star systems."""

    TECH_LEVEL_CHOICES = [
        ("type_0", "Type 0 — Sub-planetary"),
        ("type_i", "Type I — Planetary"),
        ("type_ii", "Type II — Stellar"),
        ("type_iii", "Type III — Galactic"),
    ]

    DISPOSITION_CHOICES = [
        ("unknown", "Unknown"),
        ("friendly", "Friendly"),
        ("neutral", "Neutral"),
        ("cautious", "Cautious"),
        ("hostile", "Hostile"),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    tech_level = models.CharField(
        max_length=20, choices=TECH_LEVEL_CHOICES, default="type_0",
    )
    disposition = models.CharField(
        max_length=50, choices=DISPOSITION_CHOICES, default="unknown",
    )
    portrait_url = models.CharField(max_length=500, blank=True, default="")
    is_hidden = models.BooleanField(
        default=True,
        help_text="Hidden from players until revealed.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_tech_level_display()})"


class StarSystemCivilisation(models.Model):
    """Links a civilisation to a specific star system."""

    star_system = models.ForeignKey(
        StarSystem, on_delete=models.CASCADE, related_name="civilisations",
    )
    civilisation = models.ForeignKey(
        Civilisation, on_delete=models.CASCADE, related_name="star_systems",
    )
    population_estimate = models.CharField(max_length=100, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    discovered = models.BooleanField(default=False)
    discovered_by = models.ForeignKey(
        "agencies.Agency", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="discovered_civilisations",
    )
    scan_level_required = models.IntegerField(
        default=2, help_text="Minimum scan level to discover this civilisation.",
    )

    class Meta:
        unique_together = ["star_system", "civilisation"]

    def __str__(self):
        return f"{self.civilisation.name} at {self.star_system.name}"


class Planet(models.Model):
    """A planet of interest within a star system."""

    ATMOSPHERE_CHOICES = [
        ("none", "None"),
        ("oxygen", "Oxygen-based"),
        ("methane", "Methane-based"),
        ("argon", "Argon-based"),
        ("nitrogen", "Nitrogen-based"),
        ("co2", "Carbon Dioxide"),
        ("hydrogen", "Hydrogen-Helium"),
        ("ammonia", "Ammonia"),
        ("toxic", "Toxic Mix"),
        ("unknown", "Unknown"),
    ]

    LIFE_CHOICES = [
        ("none", "No Life Detected"),
        ("prebiotic", "Prebiotic Chemistry"),
        ("bacterial", "Bacterial / Microbial"),
        ("cellular", "Cellular Organisms"),
        ("plant", "Plant Life"),
        ("animal", "Animal Life"),
        ("intelligent", "Intelligent Life"),
        ("unknown", "Unknown"),
    ]

    star_system = models.ForeignKey(
        StarSystem, on_delete=models.CASCADE, related_name="planets_of_interest",
    )
    name = models.CharField(max_length=200, help_text="e.g. 'Proxima b', 'Tau Ceti e'")
    orbital_position = models.IntegerField(
        default=1, help_text="Position from star (1 = closest)",
    )
    planet_type = models.CharField(
        max_length=50, default="terrestrial",
        help_text="e.g. terrestrial, gas_giant, ice_giant, dwarf, ocean_world",
    )
    atmosphere = models.CharField(
        max_length=20, choices=ATMOSPHERE_CHOICES, default="unknown",
    )
    atmosphere_details = models.CharField(
        max_length=200, blank=True, default="",
        help_text="Custom atmosphere composition, e.g. '78% N2, 21% O2, 1% Ar'",
    )
    life_type = models.CharField(
        max_length=20, choices=LIFE_CHOICES, default="none",
    )
    life_details = models.TextField(
        blank=True, default="",
        help_text="Description of detected life (markdown).",
    )
    temperature_range = models.CharField(
        max_length=100, blank=True, default="",
        help_text="e.g. '-20°C to 45°C'",
    )
    gravity = models.CharField(
        max_length=50, blank=True, default="",
        help_text="e.g. '0.9g', '1.2g'",
    )
    water = models.BooleanField(default=False, help_text="Liquid water detected")
    habitable = models.BooleanField(default=False, help_text="In the habitable zone")
    resources = models.JSONField(
        default=dict, blank=True,
        help_text="Planet-specific resources (override star system defaults).",
    )
    notes = models.TextField(blank=True, default="")
    is_hidden = models.BooleanField(
        default=True, help_text="Hidden from players until revealed.",
    )
    scan_level_required = models.IntegerField(
        default=1, help_text="Minimum scan level to discover this planet.",
    )
    discovered = models.BooleanField(default=False)
    discovered_by = models.ForeignKey(
        "agencies.Agency", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="discovered_planets",
    )

    class Meta:
        ordering = ["star_system", "orbital_position"]

    def __str__(self):
        return f"{self.name} ({self.star_system.name})"


class CityMap(models.Model):
    """An interactive city map for base locations and mission planning."""

    name = models.CharField(max_length=200)
    search_query = models.CharField(max_length=200, blank=True, default="")
    latitude = models.FloatField()
    longitude = models.FloatField()
    zoom = models.IntegerField(default=13)
    enabled = models.BooleanField(default=True)
    visible_to_players = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class CityMapMarker(models.Model):
    """A marker on a city map."""

    MARKER_TYPE_CHOICES = [
        ("base", "Base"),
        ("mission", "Mission"),
        ("npc", "NPC"),
        ("player", "Player"),
        ("custom", "Custom"),
    ]

    city_map = models.ForeignKey(
        CityMap, on_delete=models.CASCADE, related_name="markers",
    )
    label = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    latitude = models.FloatField()
    longitude = models.FloatField()
    marker_type = models.CharField(
        max_length=20, choices=MARKER_TYPE_CHOICES, default="custom",
    )
    color = models.CharField(max_length=20, default="#00ff88")
    icon = models.CharField(max_length=50, blank=True, default="")
    visible_to_players = models.BooleanField(default=True)
    linked_base_id = models.IntegerField(null=True, blank=True)
    linked_character_id = models.IntegerField(null=True, blank=True)
    portrait_url = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["label"]

    def __str__(self):
        return f"{self.label} ({self.marker_type})"


class PublicScanRecord(models.Model):
    """An agency's contribution to the shared public star record for a system.

    One row per (agency, system). Republishing update_or_creates; keeping data
    private = no row. ``is_false`` marks disinformation (GM-only visibility);
    each active false record raises the system's effective scan target for
    everyone. ``payload`` is the published approximate readout snapshot.
    """

    agency = models.ForeignKey(
        "agencies.Agency", on_delete=models.CASCADE, related_name="public_scan_records",
    )
    star_system = models.ForeignKey(
        "StarSystem", on_delete=models.CASCADE, related_name="public_records",
    )
    is_false = models.BooleanField(
        default=False, help_text="Disinformation (GM-only). Raises the system's scan difficulty.",
    )
    uncertainty = models.IntegerField(
        default=100, help_text="Stated uncertainty% of the published data (faked for false records).",
    )
    payload = models.JSONField(
        default=dict, help_text="Published approximate readout snapshot {resources, livable}.",
    )
    published_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["agency", "star_system"]
        ordering = ["star_system", "agency"]

    def __str__(self):
        tag = " (FALSE)" if self.is_false else ""
        return f"{self.agency_id} -> {self.star_system_id}{tag}"
