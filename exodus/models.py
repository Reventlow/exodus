"""Core models for Exodus site configuration."""

from django.db import models


def _clamp_again(value):
    """Coerce a weapon ``again`` field to one of {8, 9, 10}.

    v0.15.19 — the X-again explosion threshold is the only valid
    weapon-level lever on the attack roll: 10 (default) re-rolls on 10,
    9 re-rolls on 9 or 10, 8 re-rolls on 8/9/10. The base success
    threshold stays at 8+ regardless.

    Bad input (None, non-int strings, out-of-range ints) silently falls
    back to ``10`` so legacy / hand-edited catalogue rows behave like
    the pre-v0.15.19 code path. Used by:
      * ``SiteSettings.get_weapons`` to hydrate the read path.
      * ``exodus.views`` weapons settings POST + ``api_weapons`` /
        ``api_weapon_detail`` write paths.
    The combat module carries a deliberate local copy
    (``combat.views._clamp_again_local``) to avoid a cross-app import.
    """
    try:
        v = int(value)
    except (TypeError, ValueError):
        return 10
    if v in (8, 9, 10):
        return v
    return 10


def _clamp_reach(value):
    """Clamp the weapon ``reach`` integer to ``0..5``.

    v0.15.34 — long melee weapons get +1 dice in melee against shorter
    weapons when both attacker and target are at ``position_label =
    "engaged"``. The catalogue stores the rating as a non-negative
    integer; the resolver compares attacker vs target reach to decide
    whether the attacker gets +1 dice.

    Defaults / seeds:

    * Knuckle Buster, Knife, Phone Book, Bottle, Taser, Hammer (handle
      length only): 0
    * Baton, Chair: 1
    * (Sword, axe, machete would be 2 — none are in the seed catalogue
      yet; the GM can tune via /settings/.)
    * Firearms / thrown / grenades: 0 (no melee reach context)

    Bad input (None, non-int strings, negative) collapses to ``0``;
    values above 5 clamp down. Used by:

    * ``SiteSettings.get_weapons`` to hydrate the read path.
    * ``exodus.views`` weapons settings POST.
    * ``combat.views._actor_total_pool`` reads the hydrated value
      directly off the equipped-weapon snapshot.
    """
    try:
        v = int(value)
    except (TypeError, ValueError):
        return 0
    if v < 0:
        return 0
    if v > 5:
        return 5
    return v


def _clamp_close_range_penalty(value):
    """Clamp the close_range_penalty integer to a sensible range.

    v0.15.33 — long-barrel rifles (DMR, Scoped Rifle) take an attack
    penalty when fired at close range — they're unwieldy in CQB.
    Encoded as a per-weapon catalogue field on the firearm entries.

    Negative = unwieldy / inaccurate at close range. Positive = bonus
    (rare). Bounded ±10 to avoid pathological pool inflation. Bad input
    (None, non-int strings, garbage) collapses to ``0`` so legacy /
    hand-edited catalogue rows behave like the pre-v0.15.33 code path.

    Used by:
      * ``SiteSettings.get_weapons`` to hydrate the read path.
      * ``exodus.views`` weapons settings POST + ``api_weapons`` /
        ``api_weapon_detail`` write paths.
      * ``combat.views._actor_total_pool`` reads the hydrated value
        directly from the weapon snapshot — no cross-app import needed
        because the field is a plain int on the dict.
    """
    try:
        v = int(value)
    except (TypeError, ValueError):
        return 0
    return max(-10, min(10, v))


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
    # Star-map "tech gates" — features the players unlock in-game. Default off
    # (hidden) until the GM flips them on after the relevant discovery.
    show_ftl_route_planning = models.BooleanField(
        default=False,
        help_text="Show the FTL ROUTE PLANNING panel on the star map. Enable once players invent FTL route planning.",
    )
    show_exotic_matter = models.BooleanField(
        default=False,
        help_text="Show Exotic Matter in star-map system resource readouts. Enable once players can detect exotic matter.",
    )
    show_ftl_jumps = models.BooleanField(
        default=False,
        help_text="Enable FTL jumps: ships move between systems via a costed jump action that spends hull condition. Enable once players have FTL travel.",
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

    # FTL jump economy — all tunable numbers live here as JSON so balance
    # changes ship with no migration. Phase-1 uses maint_wear_per_jump +
    # resupply_amount; the remaining keys are inert until the Phase-2 agency
    # fuel/spares stockpile is built (cost formula + JumpLog.costs are already
    # wired for them). See SiteSettings.default_jump_economy().
    jump_economy_config = models.JSONField(
        default=dict, blank=True,
        help_text="Tunable FTL-jump economy coefficients (see default_jump_economy()).",
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
    #
    # v0.15.29 — adds "grenade" as a fifth category with extended
    # per-entry fields (radius / effect_tag / effect_duration_rounds /
    # damage_dice / damage_type / cover_resists). See
    # ``SiteSettings.default_weapons()`` and ``SiteSettings.get_weapons()``
    # for the full schema. The model-level help_text below is left
    # intentionally unchanged from v0.15.19 so the v0.15.29 release
    # ships without a Django migration (no schema diff, no SQL change).
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
            "for that weapon). For firearms, an optional again (int: "
            "8 / 9 / 10, default 10) sets the X-again explosion threshold "
            "for the attack roll — 10-again (default) re-rolls on 10, "
            "9-again re-rolls on 9 or 10, 8-again re-rolls on 8/9/10. "
            "The success threshold (8+) does NOT change between tiers — "
            "only the explosion trigger does. For firearms, an optional "
            "close_range_penalty (int, default 0; clamped ±10 via "
            "_clamp_close_range_penalty) subtracts from the attack pool "
            "when the resolved range_band is 'close' — long-barrel "
            "rifles (DMR, Scoped Rifle) are unwieldy in CQB and seed "
            "with negative values (DMR -2, Scoped Rifle -3). See "
            "SiteSettings.default_weapons() for the seed catalogue."
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
    def default_jump_economy():
        """Canonical FTL-jump economy coefficients.

        Phase-1 (active): a jump costs hull condition only —
        ``cost = max(1, round(class_maintenance * maint_wear_per_jump))`` —
        debited from ``Starship.maintenance_state``; ``resupply_amount`` is
        restored (capped at 100) when refuelling at a claimed system. Cost is
        FLAT per jump (distance is logged but not charged).

        Phase-2 (inert until the agency fuel/spares stockpile exists): the
        remaining keys map system ResourceType keys to fuel/spares pools and
        scale a resource cost by class maintenance and jump distance.
        """
        return {
            # --- Phase 1 (live) ---
            "maint_wear_per_jump": 1.0,   # multiplier on class maintenance -> condition % lost
            "resupply_amount": 100,       # condition % restored per resupply (clamped to 100)
            "max_jump_ly": 0,             # 0 = no range cap; >0 rejects longer jumps
            # --- Phase 2 (inert until agency stockpile is built) ---
            "distance_divisor": 10.0,     # reserved for distance-scaled costing
            "fuel_keys": [],              # ResourceType keys that pay the fuel cost
            "spares_keys": [],            # ResourceType keys that pay the spares cost
            "fuel_per_maint_ly": 0.0,
            "spares_per_maint_ly": 0.0,
            "base_fuel": 0,
            "base_spares": 0,
            "extract_scan_level": 2,      # min scan level to extract resources from a system
        }

    def get_jump_economy(self):
        """Saved jump-economy config merged over defaults so partial saves
        never leak missing keys to the jump endpoint."""
        merged = self.default_jump_economy()
        if isinstance(self.jump_economy_config, dict):
            merged.update({k: v for k, v in self.jump_economy_config.items() if k in merged})
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

        v0.15.33 — firearms additionally carry ``close_range_penalty:
        int`` — a signed dice modifier applied to the attack pool when
        the resolved range_band is ``close``. Negative = unwieldy in
        CQB (DMR -2, Scoped Rifle -3 by seed); positive = bonus (none
        seeded — kept for symmetry). Other firearms (Hand Gun, Assault
        Rifle, SMG, shotguns, taser cartridge) seed at 0 and are
        unaffected at close range. Non-firearm entries omit the field;
        legacy entries without it default to 0 at read time via
        ``_clamp_close_range_penalty``.
        """
        return [
            # ----- Melee --------------------------------------------------
            {"name": "Knuckle Buster", "category": "melee", "damage": "1B",
             "range": "—", "capacity": "—", "reach": 0,
             "notes": "Concealed under glove. Subdual-friendly."},
            {"name": "Knife", "category": "melee", "damage": "1L",
             "range": "—", "capacity": "—", "reach": 0,
             "notes": "Concealable. Throwable in a pinch."},
            {"name": "Baton", "category": "melee", "damage": "2B",
             "range": "—", "capacity": "—", "reach": 1,
             "notes": "Police standard. Telescopic variants extend +1 reach."},
            {"name": "Taser (Contact)", "category": "melee", "damage": "1B",
             "range": "—", "capacity": "1 charge", "reach": 0,
             "notes": "On hit: target rolls Stamina + Resolve or loses next action."},
            # ----- Improvised --------------------------------------------
            {"name": "Chair", "category": "improvised", "damage": "1B",
             "range": "—", "capacity": "—", "reach": 1,
             "notes": "−1 weapon mod. Breaks on 2+ successes."},
            {"name": "Bottle", "category": "improvised", "damage": "0B",
             "range": "—", "capacity": "—", "reach": 0,
             "notes": "Breaks on hit → broken neck = 1L improvised follow-up."},
            {"name": "Phone Book", "category": "improvised", "damage": "0B",
             "range": "—", "capacity": "—", "reach": 0,
             "notes": "Subdual-only. Spreads bashing across track without bruising."},
            {"name": "Hammer", "category": "improvised", "damage": "2B",
             "range": "—", "capacity": "—", "reach": 1,
             "notes": "Workshop tool. +1 dmg to construction-grade armour."},
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
             "close_range_penalty": -2,
             "notes": "Semi-auto designated marksman rifle. Pairs well with optics. Unwieldy at close range (-2 dice in CQB)."},
            {"name": "Shotgun", "category": "firearm", "damage": "4L close / 2L long",
             "range": "5/10/40 m", "capacity": "5+1",
             "auto_capable": False, "magazine": 6,
             "knockdown_capable": True,
             "notes": "Pump-action. Damage drops with range as shot spreads."},
            {"name": "Twin-Barrel Shotgun", "category": "firearm", "damage": "5L (both barrels)",
             "range": "5/10/40 m", "capacity": "2",
             "auto_capable": False, "magazine": 2,
             "knockdown_capable": True,
             "notes": "Fire one or both. Both = +1 damage, then full reload."},
            {"name": "Auto Shotgun", "category": "firearm", "damage": "4L",
             "range": "5/10/40 m", "capacity": "8",
             "auto_capable": True, "magazine": 8,
             "knockdown_capable": True,
             "notes": "Box-fed. Burst-fire +1 dice at close range."},
            {"name": "Scoped Rifle", "category": "firearm", "damage": "4L",
             "range": "250/500/1000 m", "capacity": "5+1",
             "auto_capable": False, "magazine": 5,
             "close_range_penalty": -3,
             "notes": "−2 initiative; +1 aim per turn (max +3) with proper scope. Utterly impractical at point-blank (-3 dice in CQB)."},
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
            # ----- Grenades (v0.15.29) ------------------------------------
            # Grenades — AOE weapons with effect tags applied to every
            # target in the blast radius. v0.15.29.
            {"name": "Frag Grenade", "category": "grenade", "damage": "3L",
             "damage_type": "L", "damage_dice": 3, "radius": "medium",
             "effect_tag": "", "effect_duration_rounds": 0, "cover_resists": True,
             "auto_capable": False, "magazine": 0, "again": 10,
             "knockdown_capable": False,
             "notes": "Standard fragmentation. Cover applies. Heavy ordnance ignores light cover."},

            {"name": "Concussion Grenade", "category": "grenade", "damage": "2B",
             "damage_type": "B", "damage_dice": 2, "radius": "close",
             "effect_tag": "stunned", "effect_duration_rounds": 1, "cover_resists": True,
             "auto_capable": False, "magazine": 0, "again": 10,
             "knockdown_capable": False,
             "notes": "Bashing damage + stunned for 1 round. Cover applies."},

            {"name": "Smoke Grenade", "category": "grenade", "damage": "—",
             "damage_type": "none", "damage_dice": 0, "radius": "large",
             "effect_tag": "smoke_cloud", "effect_duration_rounds": 3, "cover_resists": False,
             "auto_capable": False, "magazine": 0, "again": 10,
             "knockdown_capable": False,
             "notes": "No damage. Targets in blast gain smoke_cloud (acts as light concealment) for 3 rounds."},

            {"name": "Stun Grenade (Flashbang)", "category": "grenade", "damage": "—",
             "damage_type": "none", "damage_dice": 0, "radius": "medium",
             "effect_tag": "blinded", "effect_duration_rounds": 1, "cover_resists": False,
             "auto_capable": False, "magazine": 0, "again": 10,
             "knockdown_capable": False,
             "notes": "No damage. Blinded for 1 round. Bypasses cover (light/sound)."},

            {"name": "Phosphor Grenade", "category": "grenade", "damage": "4L",
             "damage_type": "L", "damage_dice": 4, "radius": "medium",
             "effect_tag": "burning", "effect_duration_rounds": 0, "cover_resists": True,
             "auto_capable": False, "magazine": 0, "again": 10,
             "knockdown_capable": False,
             "notes": "White phosphorus. 4L on detonation + burning condition (1L/round until extinguished). Brutal. Cover applies."},

            {"name": "Tear Gas Grenade", "category": "grenade", "damage": "—",
             "damage_type": "none", "damage_dice": 0, "radius": "large",
             "effect_tag": "tear_gas", "effect_duration_rounds": 4, "cover_resists": False,
             "auto_capable": False, "magazine": 0, "again": 10,
             "knockdown_capable": False,
             "notes": "No damage. tear_gas condition (-2 attack/-2 defense, coughing) for 4 rounds. Bypasses cover."},

            {"name": "EMP Grenade", "category": "grenade", "damage": "—",
             "damage_type": "none", "damage_dice": 0, "radius": "medium",
             "effect_tag": "emp_disabled", "effect_duration_rounds": 2, "cover_resists": False,
             "auto_capable": False, "magazine": 0, "again": 10,
             "knockdown_capable": False,
             "notes": "Disables electronics. emp_disabled condition (-3 to all rolls for AI / cyber characters) for 2 rounds. No effect on biological targets."},
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

        ``again`` (v0.15.19) defaults to ``10`` at read time for every
        entry that doesn't carry the field — preserves classic 10-again
        behaviour. Valid values are {8, 9, 10}; anything else clamps
        back to 10 via ``_clamp_again``. Conceptually firearm-only, but
        the field is hydrated on every row uniformly so callers don't
        have to special-case the category — the combat resolver only
        ever consults it on a firearm anyway.

        ``close_range_penalty`` (v0.15.33) defaults to ``0`` at read
        time for every entry that doesn't carry the field. Bounded
        ±10 via ``_clamp_close_range_penalty``; negative values are
        the common case (rifles unwieldy at close range). The combat
        resolver applies the value on every attack where ``range_band
        == "close"`` regardless of category, but only firearms seed
        non-zero values in the catalogue.
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
            # v0.15.29 — grenade fields. Hydrated uniformly across every
            # entry so callers can read ``entry["radius"]`` etc. without
            # KeyError on legacy / non-grenade rows. Defaults are the
            # safe "no AOE effect" values:
            #   * radius defaults to "" (informational only, no behaviour)
            #   * effect_tag defaults to "" (no condition applied)
            #   * effect_duration_rounds defaults to 0 (no expiry tag)
            #   * damage_type defaults to "" (resolver re-parses from
            #     the display ``damage`` field for non-grenade rows)
            #   * damage_dice defaults to 0 (no extra base damage; the
            #     attack pipeline reads damage from the display string
            #     for non-grenades, so 0 here is benign)
            #   * cover_resists defaults to True (legacy behaviour:
            #     cover applies to damage)
            try:
                damage_dice = int(w.get("damage_dice", 0) or 0)
            except (TypeError, ValueError):
                damage_dice = 0
            if damage_dice < 0:
                damage_dice = 0
            try:
                effect_dur = int(w.get("effect_duration_rounds", 0) or 0)
            except (TypeError, ValueError):
                effect_dur = 0
            if effect_dur < 0:
                effect_dur = 0
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
                # v0.15.19 — X-again explosion threshold. Always present
                # on the hydrated dict; defaults to 10 for legacy entries
                # and any non-firearm row. ``_clamp_again`` clamps bad
                # / out-of-range values back to 10.
                "again": _clamp_again(w.get("again", 10)),
                # v0.15.26 — knockdown capability flag. Firearm-only
                # in practice (shotguns, etc.) but hydrated uniformly so
                # callers don't have to special-case the category. Legacy
                # entries default to False; a tampered non-bool value
                # collapses via ``bool()``.
                "knockdown_capable": bool(w.get("knockdown_capable", False)),
                # v0.15.29 — grenade fields. Hydrated uniformly so
                # legacy / non-grenade rows behave like the pre-v0.15.29
                # code path (no effect, no AOE).
                "radius": (w.get("radius", "") or "") or "",
                "effect_tag": (w.get("effect_tag", "") or "") or "",
                "effect_duration_rounds": effect_dur,
                "damage_type": (w.get("damage_type", "") or "") or "",
                "damage_dice": damage_dice,
                "cover_resists": bool(w.get("cover_resists", True)),
                # v0.15.33 — close-range penalty. Always present on
                # the hydrated dict so callers can read
                # ``entry["close_range_penalty"]`` uniformly without a
                # KeyError on legacy / non-firearm rows. Conceptually
                # firearm-only (rifles unwieldy in CQB) but hydrated on
                # every row at 0 by default. ``_clamp_close_range_penalty``
                # bounds bad input to ±10 and collapses garbage to 0.
                "close_range_penalty": _clamp_close_range_penalty(
                    w.get("close_range_penalty", 0)
                ),
                # v0.15.34 — reach. Non-negative integer (0..5) used by
                # the combat resolver to grant +1 dice when an attacker
                # at engaged range has more reach than the target's
                # equipped weapon. Conceptually melee / improvised but
                # hydrated on every row at 0 by default; firearms /
                # thrown / grenades seed at 0. ``_clamp_reach`` bounds
                # bad input to ``[0, 5]`` and collapses garbage to 0.
                "reach": _clamp_reach(w.get("reach", 0)),
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
