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
            "List of weapon-entry dicts. Per-entry keys: name (str), "
            "category (str: melee | improvised | firearm | thrown), "
            "damage (str: e.g. '2L'), range (str), capacity (str), "
            "notes (str). For firearms, an optional auto_capable (bool) "
            "flag controls whether burst-fire / autofire-spread modes "
            "are offered on the attack form (legacy entries without "
            "the flag default to False at read time). For firearms, an "
            "optional magazine (int) field defines the catalogue "
            "magazine size in rounds (legacy entries without the field "
            "default to 0 at read time, which suppresses ammo tracking "
            "for that weapon). See SiteSettings.default_weapons() for "
            "the seed catalogue."
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

    # Combat NPC template catalogue. Stock stat blocks the GM can spawn
    # as mooks in encounters. Each entry: {"name", "category",
    # "combat_pool", "defense", "health_max", "armor_rating", "weapon",
    # "notes"}. Categories: guard / razor / corp / cultist / drone.
    combat_npcs = models.JSONField(
        default=list, blank=True,
        help_text=(
            "List of combat NPC stat-block entries. See "
            "SiteSettings.default_combat_npcs() for the seed catalogue "
            "and field reference."
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

        Firearms additionally carry ``auto_capable: bool`` — True iff
        the weapon supports sustained automatic fire (burst / autofire
        spread). Legacy entries without the flag default to False at
        read time via ``get_weapons``. Non-firearm entries omit the
        flag entirely (the burst-fire UI is firearm-only).

        v0.15.15 — firearms additionally carry ``magazine: int`` — the
        magazine capacity in rounds. Drives the ammo tracking system:
        each Character / NPC participant fills to ``magazine`` rounds
        on equip and on combat start; firing consumes ammo by burst
        mode (single=1 / short=3 / medium=10 / long=20); reload resets
        to ``magazine``. Non-firearm entries omit the field. Legacy
        firearm entries without the field default to ``0`` at read
        time — which the ammo system reads as "no ammo concept", so
        the weapon falls back to the pre-v0.15.15 unlimited-ammo
        behaviour without a data migration.
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
            # ``auto_capable`` controls whether the attack form offers
            # burst-fire / autofire-spread modes for this weapon. Only
            # weapons that physically support sustained automatic fire
            # carry True — semi-auto pistols, DMRs, pump shotguns and
            # bolt-action rifles stay single-shot.
            {"name": "Hand Gun", "category": "firearm", "damage": "2L",
             "range": "20/40/80 m", "capacity": "12+1",
             "auto_capable": False, "magazine": 15,
             "notes": "Concealable. 9 mm or .40 standard."},
            {"name": "Large Hand Gun", "category": "firearm", "damage": "3L",
             "range": "25/50/100 m", "capacity": "8+1",
             "auto_capable": False, "magazine": 8,
             "notes": "Magnum / .44 / .50 AE. Heavy recoil — −1 to follow-up shots."},
            {"name": "Sub Machine Gun", "category": "firearm", "damage": "2L",
             "range": "20/40/80 m", "capacity": "30",
             "auto_capable": True, "magazine": 30,
             "notes": "Burst-fire +1 dice; autofire +2 in close range."},
            {"name": "Assault Rifle", "category": "firearm", "damage": "3L",
             "range": "100/200/400 m", "capacity": "30",
             "auto_capable": True, "magazine": 30,
             "notes": "Burst-fire +1; autofire +2/+3."},
            {"name": "DMR", "category": "firearm", "damage": "4L",
             "range": "200/400/800 m", "capacity": "20",
             "auto_capable": False, "magazine": 10,
             "notes": "Semi-auto designated marksman rifle. Pairs well with optics."},
            {"name": "Shotgun", "category": "firearm", "damage": "4L close / 2L long",
             "range": "5/10/40 m", "capacity": "5+1",
             "auto_capable": False, "magazine": 6,
             "notes": "Pump-action. Damage drops with range as shot spreads."},
            {"name": "Twin-Barrel Shotgun", "category": "firearm", "damage": "5L (both barrels)",
             "range": "5/10/40 m", "capacity": "2",
             "auto_capable": False, "magazine": 2,
             "notes": "Fire one or both. Both = +1 damage, then full reload."},
            {"name": "Auto Shotgun", "category": "firearm", "damage": "4L",
             "range": "5/10/40 m", "capacity": "8",
             "auto_capable": True, "magazine": 8,
             "notes": "Box-fed. Burst-fire +1 dice at close range."},
            {"name": "Scoped Rifle", "category": "firearm", "damage": "4L",
             "range": "250/500/1000 m", "capacity": "5+1",
             "auto_capable": False, "magazine": 5,
             "notes": "−2 initiative; +1 aim per turn (max +3) with proper scope."},
            {"name": "Taser (Cartridge)", "category": "firearm", "damage": "1L + stun",
             "range": "4/8/15 m", "capacity": "1 cartridge",
             "auto_capable": False, "magazine": 1,
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
        UI handles them uniformly.

        ``auto_capable`` (v0.15.14) defaults to False at read time for
        any entry that doesn't carry the flag — legacy rows from before
        the field was introduced therefore behave as semi-auto / single-
        shot and the burst-fire UI is suppressed for them.

        ``magazine`` (v0.15.15) defaults to ``0`` at read time for any
        entry without the field. The combat ammo system reads ``0`` as
        "no magazine size on file" and skips ammo tracking for that
        entry, so legacy firearm rows behave the way they did before
        v0.15.15 (unlimited ammo) until an admin gives them a real mag
        size in /settings/.
        """
        weapons = self.weapons if isinstance(self.weapons, list) and self.weapons else self.default_weapons()
        hydrated = []
        for w in weapons:
            if not isinstance(w, dict):
                continue
            # v0.15.15 — coerce magazine to a non-negative int. Defensive
            # against catalogue rows where the field was hand-edited to
            # a non-integer string in the JSON; bad data falls back to
            # zero (which switches off ammo tracking for that weapon).
            try:
                mag = int(w.get("magazine", 0) or 0)
            except (TypeError, ValueError):
                mag = 0
            if mag < 0:
                mag = 0
            hydrated.append({
                "name": w.get("name", ""),
                "category": w.get("category", ""),
                "damage": w.get("damage", "") or "",
                "range": w.get("range", "") or "",
                "capacity": w.get("capacity", "") or "",
                "notes": w.get("notes", "") or "",
                # Read-time default — legacy entries (and every non-
                # firearm entry) collapse to False so the burst-fire UI
                # stays disabled unless explicitly opted in.
                "auto_capable": bool(w.get("auto_capable", False)),
                # v0.15.15 — magazine size in rounds. Always present on
                # the hydrated dict so callers can use ``entry.get(...)``
                # or ``entry["magazine"]`` interchangeably without a
                # KeyError on legacy data.
                "magazine": mag,
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

    @staticmethod
    def default_combat_npcs():
        """Seed catalogue of combat NPC templates (stock stat blocks).

        Each entry: ``name``, ``category`` (``guard`` / ``razor`` /
        ``corp`` / ``cultist`` / ``drone``), ``combat_pool`` (attack
        dice pool, numeric string), ``defense`` (passive defense,
        numeric string), ``health_max`` (total health boxes, numeric
        string), ``armor_rating`` (B/L subtraction or ``"—"``),
        ``weapon`` (free-text or matches catalogue), ``notes``
        (free-text flavor / mechanics).

        The ``drone`` category covers both autonomous machines and
        biological attack animals: mechanically they fight the same way
        (no morale, no intimidation, attack on command).
        """
        return [
            # Guard — civilian / building security
            {"name": "Generic Guard", "category": "guard", "combat_pool": "4", "defense": "2",
             "health_max": "7", "armor_rating": "—", "weapon": "Baton",
             "notes": "Untrained civilian-grade security. Calls for backup early."},
            {"name": "Building Security", "category": "guard", "combat_pool": "5", "defense": "3",
             "health_max": "7", "armor_rating": "1/2", "weapon": "Hand Gun",
             "notes": "Trained corporate security. Wears soft armor under uniform."},
            {"name": "Bouncer", "category": "guard", "combat_pool": "6", "defense": "2",
             "health_max": "8", "armor_rating": "—", "weapon": "Knuckle Buster",
             "notes": "Big, brutish, brawler. Subdues rather than kills."},
            # Razor — street fighters / mercenaries
            {"name": "Street Razor", "category": "razor", "combat_pool": "5", "defense": "3",
             "health_max": "7", "armor_rating": "—", "weapon": "Knife",
             "notes": "Cyberware addict, jittery, unpredictable. Will close to melee."},
            {"name": "Cyber-Razor", "category": "razor", "combat_pool": "7", "defense": "4",
             "health_max": "7", "armor_rating": "1/2", "weapon": "Large Hand Gun",
             "notes": "Augmented street operator. Reflex-boost wetware."},
            {"name": "Pit Fighter", "category": "razor", "combat_pool": "7", "defense": "4",
             "health_max": "8", "armor_rating": "—", "weapon": "Knuckle Buster",
             "notes": "Underground brawl champion. Pain Tolerance 2 (ignore wound penalty −1)."},
            # Corp — corporate security ladders
            {"name": "Corp Sec Officer", "category": "corp", "combat_pool": "6", "defense": "3",
             "health_max": "7", "armor_rating": "2/2", "weapon": "Sub Machine Gun",
             "notes": "Mid-tier corporate security. Trained, equipped, expendable."},
            {"name": "Executive Bodyguard", "category": "corp", "combat_pool": "7", "defense": "4",
             "health_max": "7", "armor_rating": "3/3", "weapon": "Hand Gun",
             "notes": "Personal protection detail. Will throw self in front of principal."},
            {"name": "Black Ops Operator", "category": "corp", "combat_pool": "9", "defense": "5",
             "health_max": "8", "armor_rating": "4/4", "weapon": "Assault Rifle",
             "notes": "Special-forces grade. Suppressed weapons, night-vision optics, IR."},
            # Cultist — zealous followers
            {"name": "Cultist Initiate", "category": "cultist", "combat_pool": "4", "defense": "2",
             "health_max": "7", "armor_rating": "—", "weapon": "Knife",
             "notes": "Fanatical, no fear of death. Charges into melee shouting prayers."},
            {"name": "Cultist Adept", "category": "cultist", "combat_pool": "6", "defense": "3",
             "health_max": "7", "armor_rating": "—", "weapon": "Hand Gun",
             "notes": "Combat-trained believer. Coordinates with other cultists."},
            {"name": "Cultist Champion", "category": "cultist", "combat_pool": "8", "defense": "4",
             "health_max": "8", "armor_rating": "3/3", "weapon": "Assault Rifle",
             "notes": "Inner-circle warrior. Carries a relic; +1 to ally morale rolls."},
            # Drone — autonomous / non-human (incl. biological attack animals)
            {"name": "Sentry Drone", "category": "drone", "combat_pool": "5", "defense": "4",
             "health_max": "5", "armor_rating": "2/2", "weapon": "Sub Machine Gun",
             "notes": "Hovering or wheeled. Cannot be intimidated. Targets nearest threat."},
            {"name": "Combat Drone", "category": "drone", "combat_pool": "7", "defense": "4",
             "health_max": "7", "armor_rating": "3/3", "weapon": "Assault Rifle",
             "notes": "Military-grade. Targets via thermal imaging — concealment less effective."},
            {"name": "Guard Dog", "category": "drone", "combat_pool": "5", "defense": "3",
             "health_max": "6", "armor_rating": "—", "weapon": "Bite (1L + grapple)",
             "notes": "Trained attack animal. Grapples on hit; victim Strength + Brawl to break."},
        ]

    def get_combat_npcs(self):
        """Return the combat NPC list, hydrated with empty strings for
        any missing fields so the UI handles legacy entries uniformly.
        Falls back to the default catalogue when the saved list is
        empty so a fresh deploy still renders templates."""
        npcs = (
            self.combat_npcs
            if isinstance(self.combat_npcs, list) and self.combat_npcs
            else self.default_combat_npcs()
        )
        hydrated = []
        for n in npcs:
            if not isinstance(n, dict):
                continue
            hydrated.append({
                "name": n.get("name", ""),
                "category": n.get("category", ""),
                "combat_pool": n.get("combat_pool", "") or "",
                "defense": n.get("defense", "") or "",
                "health_max": n.get("health_max", "") or "",
                "armor_rating": n.get("armor_rating", "") or "",
                "weapon": n.get("weapon", "") or "",
                "notes": n.get("notes", "") or "",
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
