"""Models for the personal combat application.

Phase 0 schema for gridless WoD 2.0 character-vs-character tactical
combat. Three models:

* :class:`Encounter`   — one combat instance, owns participants and log.
* :class:`Participant` — a single combatant (Character / NPC / mook),
                         owns its own snapshot of health, willpower,
                         cover, weapon, armor, conditions, etc.
* :class:`CombatLog`   — append-only event stream per encounter,
                         monotonic ``sequence`` per encounter.

Linking to :class:`characters.Character` and :class:`npcs.NPC` is via
``SET_NULL`` so deleting an actor mid-encounter snapshots the
``name`` field rather than corrupting the log. Mooks have no FK and
carry their own combat pool / defense fields directly.

Combat models reference the editable weapons / armor / cover catalogues
on :class:`exodus.SiteSettings` for later phases — the catalogue
entries are denormalised into ``weapon_data`` / ``armor_data`` JSON on
the participant so a catalogue edit mid-fight does not retroactively
mutate the encounter.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import UniqueConstraint


class Encounter(models.Model):
    """A single personal-combat instance — gridless, turn-based.

    ``round_number`` is 0 during setup and 1+ once the encounter is
    active. ``initiative_order`` is a JSON list of participant ids in
    descending tiebreak order; ``active_participant_id`` is the id of
    whose turn it currently is (denormalised pointer; the source of
    truth for ordering is ``initiative_order``).
    """

    STATUS_CHOICES = [
        ("setup", "Setup"),
        ("active", "Active"),
        ("concluded", "Concluded"),
    ]

    title = models.CharField(max_length=200)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="setup",
    )
    round_number = models.IntegerField(
        default=0,
        help_text="0 in setup, 1+ once started.",
    )
    active_participant_id = models.IntegerField(
        null=True, blank=True,
        help_text="Id of the Participant whose turn it currently is.",
    )
    initiative_order = models.JSONField(
        default=list, blank=True,
        help_text="List of Participant ids in descending initiative order.",
    )
    gm = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="combat_encounters",
    )
    # v0.15.7 — optional story-arc link. SET_NULL on delete so removing
    # a story idea does not blow up the encounters that reference it;
    # the encounter just falls back to "no arc". null/blank both allowed
    # so existing rows pre-v0.15.7 stay valid without a data migration.
    story_idea = models.ForeignKey(
        "gm_workspace.StoryIdea",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="encounters",
        help_text="Optional link to the story arc this combat belongs to.",
    )
    scene_description = models.TextField(blank=True, default="")
    location_text = models.CharField(max_length=200, blank=True, default="")
    metadata = models.JSONField(
        default=dict, blank=True,
        help_text="Free-form extension hooks (lighting, hazards, etc.).",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # v0.15.28 — GM-prep gate. New encounters created via the web form
    # default to ``True`` (set explicitly in ``encounter_create``); the
    # field-level default is ``False`` so the migration backfill keeps
    # existing rows visible on upgrade. Toggle via the RELEASE / HIDE
    # AGAIN buttons on the encounter detail page.
    is_hidden = models.BooleanField(
        default=False,
        help_text=(
            "If True, the encounter is GM-prep only — players don't see it "
            "in their list, can't access the detail page, and the WS "
            "consumer rejects their subscription. Toggle visibility via the "
            "RELEASE / HIDE button on the encounter detail page."
        ),
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Encounter #{self.pk}: {self.title}"


class Participant(models.Model):
    """A single combatant in an encounter.

    Polymorphic across Character / NPC / mook via ``participant_kind``
    plus the matching FK (``character`` / ``npc``) or, for mooks, the
    inline ``mook_*`` stat block. ``name`` is always populated so the
    log keeps something human-readable even if the FK is later
    SET_NULL'd by a delete.

    Health is a 3-track WoD 2.0 model (bashing/lethal/aggravated) —
    same shape as :class:`characters.Character`. ``defense_override``
    lets a GM pin a defense value without recomputing from the
    underlying character sheet.
    """

    KIND_CHOICES = [
        ("character", "Character"),
        ("npc", "NPC"),
        ("mook", "Mook"),
    ]

    FACTION_CHOICES = [
        ("player", "Player"),
        ("ally", "Ally"),
        ("hostile", "Hostile"),
        ("neutral", "Neutral"),
    ]

    COVER_CHOICES = [
        ("none", "None"),
        ("light", "Light"),
        ("heavy", "Heavy"),
        ("full", "Full"),
    ]

    encounter = models.ForeignKey(
        Encounter, on_delete=models.CASCADE, related_name="participants",
    )
    participant_kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    character = models.ForeignKey(
        "characters.Character",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="combat_participations",
    )
    npc = models.ForeignKey(
        "npcs.NPC",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="combat_participations",
    )
    name = models.CharField(
        max_length=200,
        help_text="Display name; copied from character/npc, or free-form for mooks.",
    )
    faction = models.CharField(
        max_length=20, choices=FACTION_CHOICES, default="hostile",
    )

    # Initiative
    initiative_score = models.IntegerField(
        null=True, blank=True,
        help_text="Composite tiebreak key for sort order in the round.",
    )
    initiative_roll = models.IntegerField(
        null=True, blank=True,
        help_text="Raw success count from the initiative roll.",
    )

    # Health track (WoD 2.0)
    health_bashing = models.IntegerField(default=0)
    health_lethal = models.IntegerField(default=0)
    health_aggravated = models.IntegerField(default=0)
    health_max = models.IntegerField(default=7)

    # Willpower
    willpower_current = models.IntegerField(default=0)
    willpower_max = models.IntegerField(default=0)

    # Mental load (WoD 2.0 stress track)
    mental_load = models.IntegerField(default=0)

    # Combat overrides
    defense_override = models.IntegerField(
        null=True, blank=True,
        help_text="Pinned defense value; null = compute from underlying sheet.",
    )

    # Cover
    cover_state = models.CharField(
        max_length=20, choices=COVER_CHOICES, default="none",
    )
    cover_entry_name = models.CharField(
        max_length=120, blank=True, default="",
        help_text="SiteSettings.cover entry name backing the current cover state.",
    )
    cover_durability = models.IntegerField(null=True, blank=True)
    cover_health = models.IntegerField(null=True, blank=True)

    # Equipped weapon (snapshot from SiteSettings.weapons)
    weapon_name = models.CharField(max_length=120, blank=True, default="")
    weapon_data = models.JSONField(
        default=dict, blank=True,
        help_text="Snapshot of the weapon stat block at the time of equipping.",
    )

    # v0.15.16 — Off-hand (dual-wielding). Mirrors weapon_name /
    # weapon_data for the second equipped weapon. Off-hand attacks
    # take a -2 dice penalty unless the actor has the Ambidextrous
    # merit. Off-hand ammo lives on a parallel ``offhand_ammo:N``
    # condition tag (no schema change for ammo state). Empty defaults
    # mean the field-add migration is safe — pre-v0.15.16 rows simply
    # have no off-hand equipped.
    offhand_weapon_name = models.CharField(max_length=120, blank=True, default="")
    offhand_weapon_data = models.JSONField(
        default=dict, blank=True,
        help_text="Snapshot of the off-hand weapon stat block at the time of equipping.",
    )

    # Worn armor (snapshot from SiteSettings.armor)
    armor_name = models.CharField(max_length=120, blank=True, default="")
    armor_data = models.JSONField(
        default=dict, blank=True,
        help_text="Snapshot of the armor stat block at the time of equipping.",
    )

    # Conditions / tags
    conditions = models.JSONField(
        default=list, blank=True,
        help_text="List of active condition tags (prone, stunned, blinded, ...).",
    )

    # Position — gridless, narrative slots ('engaged', 'short', 'long', ...).
    position_label = models.CharField(max_length=40, default="engaged")
    position_order = models.IntegerField(default=0)

    notes = models.TextField(blank=True, default="")

    # Mook-only stat block (denormalised; mooks have no Character/NPC FK)
    mook_combat_pool = models.IntegerField(null=True, blank=True)
    mook_defense = models.IntegerField(null=True, blank=True)
    mook_armor_rating = models.CharField(max_length=20, blank=True, default="")

    # Round-state flags
    surprise_immune = models.BooleanField(default=False)
    acted_this_round = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["encounter", "position_order", "id"]

    def __str__(self):
        return f"{self.name} ({self.participant_kind}) in #{self.encounter_id}"

    def clean(self):
        """Validate kind/FK consistency.

        Called explicitly from admin and (later) REST views — *not* from
        ``save``. Raw ORM writes from log-replay and rollback paths must
        be able to reconstruct historical state without re-validation.
        """
        if self.participant_kind == "character" and self.character_id is None:
            raise ValidationError(
                {"character": "character FK is required when participant_kind='character'."}
            )
        if self.participant_kind == "npc" and self.npc_id is None:
            raise ValidationError(
                {"npc": "npc FK is required when participant_kind='npc'."}
            )
        if self.participant_kind == "mook" and self.mook_combat_pool is None:
            raise ValidationError(
                {"mook_combat_pool": "mook_combat_pool is required when participant_kind='mook'."}
            )


class CombatLog(models.Model):
    """Append-only event log for an encounter.

    Every mutation (initiative, turn advance, attack, damage, condition
    set/clear, GM note, system event) writes a row here. ``sequence``
    is monotonic per encounter — the unique constraint on
    ``(encounter, sequence)`` makes that an enforced invariant rather
    than a convention. Phase 0 keeps ``action_type`` free-form;
    Phase 1+ will narrow to choices once the action vocabulary is
    pinned down.

    ``is_reverted`` is reserved for the rollback handler that lands
    in a later phase — Phase 0 always writes ``False``.
    """

    encounter = models.ForeignKey(
        Encounter, on_delete=models.CASCADE, related_name="log_entries",
    )
    sequence = models.IntegerField(
        help_text="Monotonic per encounter; unique with (encounter, sequence).",
    )
    round_number = models.IntegerField(default=0)
    actor_participant = models.ForeignKey(
        Participant,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="actor_log_entries",
    )
    target_participant = models.ForeignKey(
        Participant,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="target_log_entries",
    )
    action_type = models.CharField(
        max_length=30,
        help_text=(
            "Free-form in Phase 0; vocabulary: system, note, initiative, "
            "turn_advance, round_advance, attack, move, ability, "
            "condition_set, condition_clear, health_change, "
            "willpower_change, cover_change, weapon_change, "
            "armor_change, rollback."
        ),
    )
    data = models.JSONField(
        default=dict, blank=True,
        help_text="Action-specific payload (rolls, deltas, before/after snapshots).",
    )
    message = models.TextField(blank=True, default="")
    is_reverted = models.BooleanField(
        default=False,
        help_text="Reserved for the rollback handler in a later phase.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["encounter", "sequence", "id"]
        constraints = [
            UniqueConstraint(
                fields=["encounter", "sequence"],
                name="combat_combatlog_unique_seq",
            ),
        ]

    def __str__(self):
        return f"[{self.encounter_id}] #{self.sequence} {self.action_type}"
