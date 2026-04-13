"""Models for the spacebattle application.

A Battle is a single turn-based hex-grid engagement. Participants
are concrete Starship rows (from a player fleet or an NPC-owned
fleet), placed on axial hex coordinates (q, r). Every mutation —
move, fire, damage, status change — writes a BattleLog entry, which
is the source of truth for replay, rollback, and the MCP-driven
balance simulator.

Damage flows back to the canonical Starship record so the battle
is not a sandbox — changes persist unless the GM rolls them back
via the dedicated /rollback/ endpoint shipped in Release G.
"""

from django.conf import settings
from django.db import models


class Battle(models.Model):
    """A turn-based space combat instance on a 2D hex grid."""

    STATUS_CHOICES = [
        ("setup", "Setup"),
        ("active", "Active"),
        ("concluded", "Concluded"),
    ]

    name = models.CharField(max_length=200)
    game_date = models.CharField(
        max_length=100, blank=True, default="",
        help_text="In-game date string (matches the dispatch game_date field).",
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="setup",
    )
    grid_width = models.IntegerField(
        default=20,
        help_text="Axial hex grid width. Configurable per battle; canvas caps around 40.",
    )
    grid_height = models.IntegerField(
        default=15,
        help_text="Axial hex grid height.",
    )
    round_number = models.IntegerField(
        default=1,
        help_text="Current combat round — one full pass through the initiative order.",
    )
    active_participant_index = models.IntegerField(
        default=0,
        help_text="Index into initiative_order identifying whose turn it is.",
    )
    initiative_order = models.JSONField(
        default=list, blank=True,
        help_text="List of BattleParticipant ids in descending initiative order for the current round.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="created_battles",
    )
    notes = models.TextField(blank=True, default="")
    metadata = models.JSONField(
        default=dict, blank=True,
        help_text="Free-form JSON for extensions (terrain, objectives, house rules).",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"


class BattleParticipant(models.Model):
    """A single hull placed on the battle map.

    The starship FK is required and PROTECT-guarded — deleting a ship
    that is currently in a battle must be an explicit action, not a
    cascade side effect. Side denotes faction alignment for this
    specific battle (an NPC-owned cruiser can be flagged 'neutral'
    in one battle and 'enemies' in another).
    """

    SIDE_CHOICES = [
        ("players", "Players"),
        ("enemies", "Enemies"),
        ("neutral", "Neutral"),
    ]

    STATUS_CHOICES = [
        ("active", "Active"),
        ("damaged", "Damaged"),
        ("disabled", "Disabled"),
        ("destroyed", "Destroyed"),
    ]

    battle = models.ForeignKey(
        Battle, on_delete=models.CASCADE, related_name="participants",
    )
    starship = models.ForeignKey(
        "starships.Starship",
        on_delete=models.PROTECT,
        related_name="battle_participations",
    )
    side = models.CharField(
        max_length=20, choices=SIDE_CHOICES, default="neutral",
    )
    q = models.IntegerField(default=0, help_text="Axial hex q coordinate.")
    r = models.IntegerField(default=0, help_text="Axial hex r coordinate.")
    facing = models.IntegerField(
        default=0,
        help_text="Hex edge facing, 0-5. 0 = east, clockwise.",
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="active",
    )
    initiative_roll = models.IntegerField(
        null=True, blank=True,
        help_text="Raw d10 roll for this round before bonuses.",
    )
    initiative_result = models.IntegerField(
        null=True, blank=True,
        help_text="Final initiative after applying ship type bonus.",
    )
    token_color = models.CharField(
        max_length=20, blank=True, default="",
        help_text="Override colour for the canvas token. Empty = side default.",
    )
    token_icon = models.CharField(
        max_length=20, blank=True, default="",
        help_text="Unicode glyph or short label rendered on the token.",
    )
    notes = models.TextField(blank=True, default="")
    position_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["battle", "position_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["battle", "starship"],
                name="unique_starship_per_battle",
            ),
        ]

    def __str__(self):
        return f"{self.starship.name} @ ({self.q},{self.r}) [{self.side}]"


class BattleTerrain(models.Model):
    """A single terrain feature occupying one hex of a battle grid.

    Visual-only in v0.14.7 — the canvas renders a coloured hex fill
    and glyph but mechanics (LOS blocking, movement cost, damage per
    turn) are GM-adjudicated. The metadata JSONField is reserved for
    a future rules engine to hook into without further migrations.
    """

    TERRAIN_CHOICES = [
        ("asteroid", "Asteroid Field"),
        ("nebula", "Nebula"),
        ("debris", "Debris Field"),
        ("planet", "Planet / Moon"),
        ("sun", "Star / Sun Hazard"),
        ("gravity_well", "Gravity Well"),
        ("minefield", "Minefield"),
        ("station", "Station / Platform"),
        ("zone", "Scenario Zone"),
        ("custom", "Custom"),
    ]

    battle = models.ForeignKey(
        Battle, on_delete=models.CASCADE, related_name="terrain_features",
    )
    q = models.IntegerField()
    r = models.IntegerField()
    terrain_type = models.CharField(
        max_length=30, choices=TERRAIN_CHOICES, default="asteroid",
    )
    display_name = models.CharField(max_length=200, blank=True, default="")
    color = models.CharField(
        max_length=20, blank=True, default="",
        help_text="Override hex colour. Empty = default per terrain type.",
    )
    icon = models.CharField(
        max_length=20, blank=True, default="",
        help_text="Override unicode glyph. Empty = default per terrain type.",
    )
    notes = models.TextField(blank=True, default="")
    metadata = models.JSONField(
        default=dict, blank=True,
        help_text="Rule hooks (blocks_los, movement_cost, damage_per_turn) — reserved.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["battle", "r", "q"]
        constraints = [
            models.UniqueConstraint(
                fields=["battle", "q", "r"],
                name="unique_terrain_per_hex",
            ),
        ]

    def __str__(self):
        return f"{self.get_terrain_type_display()} @ ({self.q},{self.r})"


class TerrainTemplate(models.Model):
    """A reusable stamp — a relative pattern of terrain hexes.

    Stamping a template at origin (q0, r0) creates BattleTerrain rows
    at (q0 + offset_q, r0 + offset_r) for every entry in `hexes`.
    Templates live outside any specific battle so they can be reused.
    """

    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True, default="")
    hexes = models.JSONField(
        default=list, blank=True,
        help_text=(
            "List of {q, r, terrain_type, display_name?, color?, icon?} "
            "with q/r as offsets from the template origin (0,0)."
        ),
    )
    created_by = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="terrain_templates",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({len(self.hexes or [])} hexes)"


class BattleMap(models.Model):
    """A full saved space map — grid dims + terrain, reusable across battles.

    Apply-to-battle copies the grid size and the terrain list onto a
    target Battle, optionally wiping existing terrain first. Useful
    for prepping set-piece engagements before a session.
    """

    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True, default="")
    grid_width = models.IntegerField(default=20)
    grid_height = models.IntegerField(default=15)
    terrain = models.JSONField(
        default=list, blank=True,
        help_text=(
            "Absolute-coordinate terrain list: "
            "[{q, r, terrain_type, display_name?, color?, icon?, notes?}]."
        ),
    )
    created_by = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="battle_maps",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.grid_width}x{self.grid_height})"


class BattleLog(models.Model):
    """Append-only event log.

    Every action, move, fire declaration, damage application, status
    change, GM note, and system event gets a row here. The log is
    the basis for replay, rollback (reverse apply each entry), and
    the MCP-driven balance simulator which scores outcomes off log
    aggregates.
    """

    ACTION_CHOICES = [
        ("system", "System"),
        ("note", "GM Note"),
        ("initiative", "Initiative"),
        ("turn_advance", "Turn Advance"),
        ("move", "Move"),
        ("fire", "Fire"),
        ("damage", "Damage"),
        ("status_change", "Status Change"),
        ("rollback", "Rollback"),
    ]

    battle = models.ForeignKey(
        Battle, on_delete=models.CASCADE, related_name="log_entries",
    )
    round_number = models.IntegerField(default=1)
    actor_participant = models.ForeignKey(
        BattleParticipant,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="log_entries",
    )
    action_type = models.CharField(
        max_length=30, choices=ACTION_CHOICES, default="note",
    )
    data = models.JSONField(
        default=dict, blank=True,
        help_text="Action-specific payload: coordinates, weapon key, damage deltas, etc.",
    )
    message = models.TextField(blank=True, default="")
    is_reverted = models.BooleanField(
        default=False,
        help_text="Set by the Release G rollback handler when an entry has been undone.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["battle", "id"]

    def __str__(self):
        return f"[{self.battle_id}] {self.action_type} r{self.round_number}"
