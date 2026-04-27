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

    # Armor catalogue. List of {"name", "category", "rating", "str_min",
    # "penalty", "notes"} dicts. Categories: light, medium, heavy, vacuum.
    armor = models.JSONField(
        default=list, blank=True,
        help_text=(
            "List of armor entries. See SiteSettings.default_armor() for "
            "the seed catalogue and field reference."
        ),
    )

    # Cover catalogue. Each entry has a tier (light / heavy / full),
    # durability + health stats, and free-text notes.
    cover = models.JSONField(
        default=list, blank=True,
        help_text=(
            "List of cover entries. See SiteSettings.default_cover() for "
            "the seed catalogue and field reference."
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
        """Seed catalogue of personal handheld weapons with WoD 2.0 stats.

        Each entry: ``name``, ``category``, ``damage`` (e.g. "1L", "2B"),
        ``range`` ("—" for melee; ``S/M/L`` metres for ranged or
        ``Str ×3/×6/×12`` for thrown), ``capacity`` ("—" for melee/thrown
        or e.g. "12+1" for firearms), and free-text ``notes``.
        """
        return [
            # ----- Melee --------------------------------------------------
            {"name": "Knuckle Buster", "category": "melee", "damage": "1B",
             "range": "—", "capacity": "—", "notes": "Concealed under glove. Subdual-friendly."},
            {"name": "Knife", "category": "melee", "damage": "1L",
             "range": "—", "capacity": "—", "notes": "Concealable. Throwable in a pinch."},
            {"name": "Baton", "category": "melee", "damage": "2B",
             "range": "—", "capacity": "—", "notes": "Police standard. Telescopic variants extend +1 reach."},
            {"name": "Taser (Contact)", "category": "melee", "damage": "1B",
             "range": "—", "capacity": "1 charge",
             "notes": "On hit: target rolls Stamina + Resolve or loses next action."},
            # ----- Improvised --------------------------------------------
            {"name": "Chair", "category": "improvised", "damage": "1B",
             "range": "—", "capacity": "—", "notes": "−1 weapon mod. Breaks on 2+ successes."},
            {"name": "Bottle", "category": "improvised", "damage": "0B",
             "range": "—", "capacity": "—",
             "notes": "Breaks on hit → broken neck = 1L improvised follow-up."},
            {"name": "Phone Book", "category": "improvised", "damage": "0B",
             "range": "—", "capacity": "—", "notes": "Subdual-only. Spreads bashing across track without bruising."},
            {"name": "Hammer", "category": "improvised", "damage": "2B",
             "range": "—", "capacity": "—", "notes": "Workshop tool. +1 dmg to construction-grade armour."},
            # ----- Firearm ------------------------------------------------
            {"name": "Hand Gun", "category": "firearm", "damage": "2L",
             "range": "20/40/80 m", "capacity": "12+1",
             "notes": "Concealable. 9 mm or .40 standard."},
            {"name": "Large Hand Gun", "category": "firearm", "damage": "3L",
             "range": "25/50/100 m", "capacity": "8+1",
             "notes": "Magnum / .44 / .50 AE. Heavy recoil — −1 to follow-up shots."},
            {"name": "Sub Machine Gun", "category": "firearm", "damage": "2L",
             "range": "20/40/80 m", "capacity": "30",
             "notes": "Burst-fire +1 dice; autofire +2 in close range."},
            {"name": "Assault Rifle", "category": "firearm", "damage": "3L",
             "range": "100/200/400 m", "capacity": "30",
             "notes": "Burst-fire +1; autofire +2/+3."},
            {"name": "DMR", "category": "firearm", "damage": "4L",
             "range": "200/400/800 m", "capacity": "20",
             "notes": "Semi-auto designated marksman rifle. Pairs well with optics."},
            {"name": "Shotgun", "category": "firearm", "damage": "4L close / 2L long",
             "range": "5/10/40 m", "capacity": "5+1",
             "notes": "Pump-action. Damage drops with range as shot spreads."},
            {"name": "Twin-Barrel Shotgun", "category": "firearm", "damage": "5L (both barrels)",
             "range": "5/10/40 m", "capacity": "2",
             "notes": "Fire one or both. Both = +1 damage, then full reload."},
            {"name": "Auto Shotgun", "category": "firearm", "damage": "4L",
             "range": "5/10/40 m", "capacity": "8",
             "notes": "Box-fed. Burst-fire +1 dice at close range."},
            {"name": "Scoped Rifle", "category": "firearm", "damage": "4L",
             "range": "250/500/1000 m", "capacity": "5+1",
             "notes": "−2 initiative; +1 aim per turn (max +3) with proper scope."},
            {"name": "Taser (Cartridge)", "category": "firearm", "damage": "1L + stun",
             "range": "4/8/15 m", "capacity": "1 cartridge",
             "notes": "On hit: Stamina + Resolve or stunned for [successes] turns."},
            # ----- Thrown -------------------------------------------------
            {"name": "Throwing Knife", "category": "thrown", "damage": "1L",
             "range": "Str ×3 / ×6 / ×12 m", "capacity": "—",
             "notes": "Recoverable on retrieval. Concealable."},
            {"name": "Throwing Axe", "category": "thrown", "damage": "2L",
             "range": "Str ×3 / ×6 / ×12 m", "capacity": "—",
             "notes": "Heavy — Str 2 minimum. Devastating at close range."},
        ]

    def get_weapons(self):
        """Return the weapons list, hydrating any legacy entries that
        only have ``name`` + ``category`` with empty stat strings so the
        UI handles them uniformly."""
        weapons = self.weapons if isinstance(self.weapons, list) and self.weapons else self.default_weapons()
        hydrated = []
        for w in weapons:
            if not isinstance(w, dict):
                continue
            hydrated.append({
                "name": w.get("name", ""),
                "category": w.get("category", ""),
                "damage": w.get("damage", "") or "",
                "range": w.get("range", "") or "",
                "capacity": w.get("capacity", "") or "",
                "notes": w.get("notes", "") or "",
            })
        return hydrated

    @staticmethod
    def default_armor():
        """Seed catalogue of armor with WoD 2.0 stats.

        Each entry: ``name``, ``category`` (``light`` / ``medium`` /
        ``heavy`` / ``vacuum``), ``rating`` (``B/L`` subtraction, e.g.
        ``"1/2"``), ``str_min`` (Strength minimum to wear without
        penalty, ``"—"`` if none), ``penalty`` (combined Defense /
        Speed / Initiative penalty, e.g. ``"−1 Def, −1 Spd"``), and
        free-text ``notes``.
        """
        return [
            # ----- Light --------------------------------------------------
            {"name": "Reinforced Coat", "category": "light", "rating": "1/0",
             "str_min": "—", "penalty": "—",
             "notes": "Concealable. Slash-resistant lining; bullets pass."},
            {"name": "Kevlar Vest", "category": "light", "rating": "1/2",
             "str_min": "—", "penalty": "—",
             "notes": "Soft armor. Concealable under street clothes."},
            {"name": "Tactical Vest", "category": "light", "rating": "2/2",
             "str_min": "—", "penalty": "−1 Def",
             "notes": "Visible. MOLLE attachments. Civilian-legal."},
            # ----- Medium -------------------------------------------------
            {"name": "Riot Gear", "category": "medium", "rating": "2/3",
             "str_min": "1", "penalty": "−1 Def, −1 Spd",
             "notes": "Helmet + chest + limb plates. Police standard."},
            {"name": "Plate Carrier", "category": "medium", "rating": "3/3",
             "str_min": "2", "penalty": "−1 Def, −1 Spd",
             "notes": "Ceramic / steel inserts. Visible. Combat-grade."},
            {"name": "EOD Suit", "category": "medium", "rating": "4/4",
             "str_min": "2", "penalty": "−2 Def, −2 Spd",
             "notes": "Bomb disposal. Helmet + groin plate. Limited mobility."},
            # ----- Heavy --------------------------------------------------
            {"name": "Full Ballistic", "category": "heavy", "rating": "4/4",
             "str_min": "2", "penalty": "−2 Def, −1 Spd",
             "notes": "Full body coverage. Modern military issue."},
            {"name": "Combat Plate", "category": "heavy", "rating": "5/5",
             "str_min": "3", "penalty": "−2 Def, −2 Spd",
             "notes": "Hardened ceramic + composite. Visible armor signature."},
            {"name": "Powered Exo-Frame", "category": "heavy", "rating": "5/5",
             "str_min": "—", "penalty": "−1 Def",
             "notes": "Powered assist (+2 effective Str). 8h charge. Loud."},
            # ----- Vacuum -------------------------------------------------
            {"name": "EVA Suit", "category": "vacuum", "rating": "1/1",
             "str_min": "—", "penalty": "−1 Def",
             "notes": "Sealed pressure suit. 6h life support. Industrial standard."},
            {"name": "Hardsuit", "category": "vacuum", "rating": "3/3",
             "str_min": "2", "penalty": "−2 Def, −1 Spd",
             "notes": "Sealed combat suit. 12h life support. Helmet HUD."},
            {"name": "Industrial Hardsuit", "category": "vacuum", "rating": "4/4",
             "str_min": "2", "penalty": "−2 Def, −2 Spd",
             "notes": "Sealed. Powered manipulators (+2 Str for lifting). 24h life support."},
        ]

    def get_armor(self):
        """Return the armor list, hydrated with empty strings for any
        missing fields so the UI handles legacy entries uniformly."""
        armor = self.armor if isinstance(self.armor, list) and self.armor else self.default_armor()
        hydrated = []
        for a in armor:
            if not isinstance(a, dict):
                continue
            hydrated.append({
                "name": a.get("name", ""),
                "category": a.get("category", ""),
                "rating": a.get("rating", "") or "",
                "str_min": a.get("str_min", "") or "",
                "penalty": a.get("penalty", "") or "",
                "notes": a.get("notes", "") or "",
            })
        return hydrated

    @staticmethod
    def default_cover():
        """Seed catalogue of cover types with WoD 2.0 stats.

        Each entry: ``name``, ``tier`` (``light`` / ``heavy`` / ``full``;
        light = −2, heavy = −4, full = cannot target), ``durability``
        (numeric string), ``health`` (numeric string), free-text ``notes``.
        Damage exceeding Durability eats Health; cover collapses at Health 0.
        """
        return [
            # Light cover (−2 to attacker)
            {"name": "Wooden chair / door", "tier": "light",
             "durability": "1", "health": "4",
             "notes": "Splinters within 2 turns of sustained fire."},
            {"name": "Drywall partition", "tier": "light",
             "durability": "1", "health": "3",
             "notes": "Bullets pass through cleanly at heavy calibre."},
            {"name": "Vehicle door", "tier": "light",
             "durability": "2", "health": "5",
             "notes": "Light cover. Engine block separately = heavy cover."},
            # Heavy cover (−4 to attacker)
            {"name": "Vehicle engine block", "tier": "heavy",
             "durability": "3", "health": "8",
             "notes": "Heavy cover front-on. Other angles = light cover."},
            {"name": "Sandbag stack", "tier": "heavy",
             "durability": "3", "health": "6",
             "notes": "Field-expedient. Stops most small-arms fire."},
            {"name": "Brick wall", "tier": "heavy",
             "durability": "4", "health": "8",
             "notes": "Crumbles under sustained .50-cal."},
            # Full cover (cannot target directly)
            {"name": "Concrete wall", "tier": "full",
             "durability": "5", "health": "10",
             "notes": "Demolition-grade ordnance to breach."},
            {"name": "Reinforced bulkhead", "tier": "full",
             "durability": "7", "health": "15",
             "notes": "Ship-grade armor. AT weapons required."},
        ]

    def get_cover(self):
        """Return the cover list, hydrated with empty strings for any
        missing fields so the UI handles legacy entries uniformly."""
        cover = self.cover if isinstance(self.cover, list) and self.cover else self.default_cover()
        hydrated = []
        for c in cover:
            if not isinstance(c, dict):
                continue
            hydrated.append({
                "name": c.get("name", ""),
                "tier": c.get("tier", ""),
                "durability": c.get("durability", "") or "",
                "health": c.get("health", "") or "",
                "notes": c.get("notes", "") or "",
            })
        return hydrated

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
