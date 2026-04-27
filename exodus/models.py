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
    CLASS_RESTRICTION_CHOICES = [
        ("", "All Classes"),
        ("fixer", "Fixer"),
        ("soldier", "Soldier"),
        ("science", "Science"),
        ("engineer", "Engineer"),
        ("ai", "AI"),
    ]

    class_restriction = models.CharField(
        max_length=20, choices=CLASS_RESTRICTION_CHOICES, blank=True, default="",
        help_text="If set, only characters of this class can take this merit. Blank = available to all.",
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
    lock_comms = models.BooleanField(
        default=True,
        help_text="Lock comms and cyber terminal for non-superusers (unlock during game sessions).",
    )
    show_world_map = models.BooleanField(
        default=True,
        help_text="Show WORLD MAP link in navigation for all players.",
    )
    show_star_map = models.BooleanField(
        default=False,
        help_text="Show STAR MAP link in navigation for all players.",
    )
    show_starships = models.BooleanField(
        default=False,
        help_text="Show STARSHIPS link in navigation and let players open the /starships/ page.",
    )
    show_council = models.BooleanField(
        default=True,
        help_text="Show COUNCIL link in navigation.",
    )
    council_mode = models.CharField(
        max_length=20,
        default="agency",
        help_text="Council voting mode: 'agency' (agencies vote) or 'player' (individual players/NPCs vote).",
    )
    enforce_ship_slot_budget = models.BooleanField(
        default=False,
        help_text=(
            "If true, the starship class editor rejects designs that exceed "
            "their ShipType's slot budget. If false, it only warns — useful "
            "for sketching in-progress designs."
        ),
    )

    # Base-building class restrictions: { "soldier": True, ... } means that
    # class's locked items (required_class="soldier") are unlocked for all
    # characters. Missing key or False = restriction still enforced.
    class_unlock_flags = models.JSONField(
        default=dict, blank=True,
        help_text=(
            "Per-class base-building unlock flags. If a class key is True, "
            "items flagged required_class=<that class> become available to "
            "all characters. Use when the campaign has no character of that "
            "class so the mechanics are not inaccessible."
        ),
    )

    # Nav bar label customisation
    label_dispatch = models.CharField(max_length=50, default="DISPATCH", blank=True)
    label_players = models.CharField(max_length=50, default="PLAYERS", blank=True)
    label_agencies = models.CharField(max_length=50, default="AGENCIES", blank=True)
    label_council = models.CharField(max_length=50, default="COUNCIL", blank=True)
    label_npcs = models.CharField(max_length=50, default="NPC'S", blank=True)
    label_comms = models.CharField(max_length=50, default="COMMS", blank=True)

    # Clearance Gate (login surface) presentation tweaks. JSON blob with the
    # full schema produced by ``default_tweaks()``. The login template embeds
    # this directly into the page; the in-browser code reads it as initial
    # state. Persisted here so superusers can rebrand the gate without code.
    tweaks = models.JSONField(
        default=dict, blank=True,
        help_text=(
            "Login screen presentation. Keys: palette, backdrop, "
            "map_intensity, show_radar, show_nodes, rain_style, rain_density, "
            "rain_speed, scanlines, vignette, show_rails, agency_name, "
            "op_codename. See SiteSettings.default_tweaks() for defaults."
        ),
    )

    # Handheld weapons catalogue. List of {"name": str, "category": str}.
    # Categories: melee, improvised, firearm, thrown. Edited via
    # /settings/ → COMBAT → WEAPONS.
    weapons = models.JSONField(
        default=list, blank=True,
        help_text=(
            "List of {name, category} dicts. Categories: melee, improvised, "
            "firearm, thrown. See SiteSettings.default_weapons() for the "
            "seed catalogue."
        ),
    )

    class Meta:
        verbose_name = "Site Settings"
        verbose_name_plural = "Site Settings"

    def __str__(self):
        return "Site Settings"

    @staticmethod
    def default_tweaks():
        """Canonical defaults — EMERALD palette, OPS_MAP backdrop, all FX on."""
        return {
            "palette": "emerald",          # emerald | amber | ice | blood | bone
            "backdrop": "ops_map",         # ops_map | code_rain | plain
            "map_intensity": 1.0,          # 0.0 .. 1.0  (slider 0..100)
            "show_radar": True,
            "show_nodes": True,
            "rain_style": "katakana",      # katakana | hex | binary | ascii
            "rain_density": 1.0,           # 0.0 .. 1.0  (slider 0..100)
            "rain_speed": 1.0,             # 0.0 .. 1.0  (slider 0..100)
            "scanlines": True,
            "vignette": True,
            "show_rails": True,
            "agency_name": "BLACKLOG.NET",
            "op_codename": "OMEGA-7",
            # IANA timezone shown in the header strip clock. UTC default
            # so the strip never shifts unless an admin explicitly picks
            # a regional zone.
            "timezone": "UTC",
        }

    def get_tweaks(self):
        """Return saved tweaks merged over defaults so partial saves never
        leak missing keys to the front-end."""
        merged = self.default_tweaks()
        if isinstance(self.tweaks, dict):
            merged.update({k: v for k, v in self.tweaks.items() if k in merged})
        return merged

    @staticmethod
    def default_weapons():
        """Seed catalogue of personal handheld weapons. Edited via the
        WEAPONS section of /settings/."""
        return [
            # Melee — close-combat tools
            {"name": "Knuckle Buster", "category": "melee"},
            {"name": "Knife", "category": "melee"},
            {"name": "Baton", "category": "melee"},
            {"name": "Taser (Contact)", "category": "melee"},
            # Improvised — anything-goes pickup weapons
            {"name": "Chair", "category": "improvised"},
            {"name": "Bottle", "category": "improvised"},
            {"name": "Phone Book", "category": "improvised"},
            {"name": "Hammer", "category": "improvised"},
            # Firearms
            {"name": "Hand Gun", "category": "firearm"},
            {"name": "Large Hand Gun", "category": "firearm"},
            {"name": "Sub Machine Gun", "category": "firearm"},
            {"name": "Assault Rifle", "category": "firearm"},
            {"name": "DMR", "category": "firearm"},
            {"name": "Shotgun", "category": "firearm"},
            {"name": "Twin-Barrel Shotgun", "category": "firearm"},
            {"name": "Auto Shotgun", "category": "firearm"},
            {"name": "Scoped Rifle", "category": "firearm"},
            {"name": "Taser (Cartridge)", "category": "firearm"},
            # Thrown
            {"name": "Throwing Knife", "category": "thrown"},
            {"name": "Throwing Axe", "category": "thrown"},
        ]

    def get_weapons(self):
        """Return the weapons list. Empty list seeds with the default
        catalogue so a fresh deploy ships with a useful starter set."""
        if isinstance(self.weapons, list) and self.weapons:
            return self.weapons
        return self.default_weapons()

    def save(self, *args, **kwargs):
        """Enforce singleton: always use pk=1. Also normalise tweaks so the
        on-disk JSON always has the full schema."""
        self.pk = 1
        # Validate / normalise tweaks blob on every save.
        if not isinstance(self.tweaks, dict):
            self.tweaks = {}
        merged = self.default_tweaks()
        merged.update({k: v for k, v in (self.tweaks or {}).items() if k in merged})
        self.tweaks = merged
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Prevent deletion of the singleton."""
        pass

    @classmethod
    def load(cls):
        """Load or create the singleton instance."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
