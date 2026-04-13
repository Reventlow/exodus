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
