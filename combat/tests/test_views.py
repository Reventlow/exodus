"""Integration tests for combat/views.py — the most-used view paths.

Covers:

* Encounter CRUD (create / release / delete + visibility gates)
* Initiative (single, all, clear, per-round re-roll)
* Attack resolution (ammo, cover, surprise round, alert immunity)
* Permission gates (GM-only, GM-or-owner, NPC/mook gating)
* Player-ready gate at start
* Burn tick (GM manual)
* Knockdown auto-trigger
* Grenades (inventory, EMP immunity, scatter)

All tests use Django's transactional :class:`TestCase` — fast and
isolated. Setup helpers live in ``combat/tests/factories.py``.

TODO (future release): WebSocket consumer auth tests via
``channels.testing.WebsocketCommunicator``. Skipped in v0.15.35 to
keep the dependency surface minimal.
"""

from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse

from combat.models import CombatLog, Encounter, Participant
from combat.tests.factories import (
    make_character,
    make_encounter,
    make_npc,
    make_participant,
    make_user,
)


# ---------------------------------------------------------------------------
# Encounter CRUD + visibility gates
# ---------------------------------------------------------------------------


class EncounterCRUDTests(TestCase):
    """Tests for encounter create / release / delete + visibility."""

    def setUp(self):
        self.gm = make_user(is_superuser=True)
        self.player = make_user()
        self.client = Client()

    def test_create_encounter_defaults_hidden(self):
        """A GM POST to ``encounter_create`` defaults ``is_hidden=True``.

        Pre-v0.15.28 encounters published immediately. The GM-prep flow
        introduced in v0.15.28 makes the new row hidden by default;
        this test pins that behaviour so a refactor doesn't silently
        re-publish encounters at creation time.
        """
        self.client.force_login(self.gm)
        resp = self.client.post(
            reverse("combat:create"), {"title": "Op Test"},
        )
        # 302 redirect to detail.
        self.assertEqual(resp.status_code, 302)
        encounter = Encounter.objects.get(title="Op Test")
        self.assertTrue(encounter.is_hidden)

    def test_release_encounter_makes_visible(self):
        """``release_encounter`` flips ``is_hidden`` to False."""
        encounter = make_encounter(gm=self.gm, is_hidden=True)
        self.client.force_login(self.gm)
        resp = self.client.post(
            reverse("combat:release", kwargs={"pk": encounter.pk}),
        )
        self.assertEqual(resp.status_code, 302)
        encounter.refresh_from_db()
        self.assertFalse(encounter.is_hidden)

    def test_player_cannot_see_hidden_encounter_in_list(self):
        """The list page filters out hidden encounters for non-GMs."""
        encounter = make_encounter(gm=self.gm, is_hidden=True)
        # Player must own a Character that's a Participant — otherwise
        # they wouldn't see the encounter even when published.
        char = make_character(owner=self.player)
        make_participant(encounter, character=char, kind="character")
        self.client.force_login(self.player)
        resp = self.client.get(reverse("combat:list"))
        self.assertEqual(resp.status_code, 200)
        # The list-page context excludes hidden rows for the player.
        self.assertNotIn(encounter, resp.context["encounters"])

    def test_player_403_on_hidden_encounter_detail(self):
        """Direct URL access to a hidden encounter returns 403 for players."""
        encounter = make_encounter(gm=self.gm, is_hidden=True)
        char = make_character(owner=self.player)
        make_participant(encounter, character=char, kind="character")
        self.client.force_login(self.player)
        resp = self.client.get(
            reverse("combat:detail", kwargs={"pk": encounter.pk}),
        )
        self.assertEqual(resp.status_code, 403)

    def test_gm_can_delete_encounter(self):
        """``encounter_delete`` removes the row + cascades to participants."""
        encounter = make_encounter(gm=self.gm)
        char = make_character(owner=self.player)
        p = make_participant(encounter, character=char, kind="character")
        self.client.force_login(self.gm)
        resp = self.client.post(
            reverse("combat:delete", kwargs={"pk": encounter.pk}),
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Encounter.objects.filter(pk=encounter.pk).exists())
        # Cascade should have removed the participant too.
        self.assertFalse(Participant.objects.filter(pk=p.pk).exists())


# ---------------------------------------------------------------------------
# Initiative — single + clear + per-round re-roll
# ---------------------------------------------------------------------------


class InitiativeTests(TestCase):
    """Tests for the initiative-roll lifecycle."""

    def setUp(self):
        self.gm = make_user(is_superuser=True)
        self.player = make_user()
        self.client = Client()
        self.encounter = make_encounter(gm=self.gm)
        self.char = make_character(owner=self.player)
        self.participant = make_participant(
            self.encounter, character=self.char, kind="character",
            name=self.char.name, faction="player",
        )

    def test_roll_initiative_for_one_participant(self):
        """A single roll sets ``initiative_score`` and ``initiative_roll``."""
        self.client.force_login(self.gm)
        resp = self.client.post(
            reverse("combat:roll_initiative", kwargs={
                "pk": self.encounter.pk,
                "participant_id": self.participant.pk,
            }),
        )
        self.assertEqual(resp.status_code, 302)
        self.participant.refresh_from_db()
        self.assertIsNotNone(self.participant.initiative_score)
        self.assertIsNotNone(self.participant.initiative_roll)
        # Scores are mod + d10. d10 ∈ [1, 10] so score must be > 0
        # for any non-zero modifier (our default character has Dex 2 +
        # Composure 2 = mod 4).
        self.assertGreater(self.participant.initiative_score, 0)

    def test_clear_initiative_resets_to_setup(self):
        """``clear_initiative`` wipes scores and reverts active → setup."""
        # Drop the encounter into 'active' first; clear should pull it
        # back to setup.
        self.encounter.status = "active"
        self.encounter.round_number = 3
        self.encounter.save(update_fields=["status", "round_number"])
        self.participant.initiative_score = 12
        self.participant.initiative_roll = 7
        self.participant.save()
        self.client.force_login(self.gm)
        self.client.post(
            reverse("combat:clear_initiative",
                    kwargs={"pk": self.encounter.pk}),
        )
        self.encounter.refresh_from_db()
        self.participant.refresh_from_db()
        self.assertEqual(self.encounter.status, "setup")
        self.assertEqual(self.encounter.round_number, 0)
        self.assertIsNone(self.participant.initiative_score)
        self.assertIsNone(self.participant.initiative_roll)

    def test_per_round_reroll_at_round_advance(self):
        """v0.15.32 — initiative re-rolls every round at the boundary.

        Set up a single-participant active encounter at round 1 with a
        known initiative score. Click NEXT TURN; since there's only one
        in the order the round rolls over, which triggers the re-roll
        branch in ``_advance_turn_pointer``. The participant's
        ``initiative_score`` should be re-rolled (could randomly be the
        same value, so we instead assert that a ``round_advance`` log
        row was written carrying a ``rolled`` payload).
        """
        # Configure as if the encounter is active and this participant
        # is the only one in the order.
        self.encounter.status = "active"
        self.encounter.round_number = 1
        self.encounter.initiative_order = [self.participant.pk]
        self.encounter.active_participant_id = self.participant.pk
        self.encounter.save()
        self.participant.initiative_score = 8
        self.participant.initiative_roll = 4
        self.participant.save()
        self.client.force_login(self.gm)
        self.client.post(
            reverse("combat:next_turn", kwargs={"pk": self.encounter.pk}),
        )
        self.encounter.refresh_from_db()
        self.assertEqual(self.encounter.round_number, 2)
        # A round_advance log row carrying a 'rolled' payload key
        # should exist after the boundary fires.
        round_log = CombatLog.objects.filter(
            encounter=self.encounter, action_type="round_advance",
        ).first()
        self.assertIsNotNone(round_log)
        self.assertIn("rolled", round_log.data)


# ---------------------------------------------------------------------------
# Attack resolution — ammo, cover, surprise, alert immunity
# ---------------------------------------------------------------------------


class AttackResolutionTests(TestCase):
    """Tests for the ``attack`` view's main branches."""

    def setUp(self):
        self.gm = make_user(is_superuser=True)
        self.player = make_user()
        self.client = Client()
        self.encounter = make_encounter(
            gm=self.gm, status="active", round_number=1,
        )
        # Attacker is a Character so the player can drive it.
        self.char = make_character(owner=self.player)
        # Equip a firearm with 5 rounds in the magazine via condition tag.
        firearm = {
            "name": "Hand Gun",
            "category": "firearm",
            "damage": "2L",
            "magazine": 5,
            "auto_capable": False,
            "again": 10,
        }
        self.attacker = make_participant(
            self.encounter, character=self.char, kind="character",
            name=self.char.name, faction="player",
            weapon_name="Hand Gun", weapon_data=firearm,
            conditions=["ammo:5"],
        )
        # Make this attacker the active actor in the order.
        self.encounter.active_participant_id = self.attacker.pk
        self.encounter.initiative_order = [self.attacker.pk]
        self.encounter.save()

        # Target is a mook so we don't need a Character/NPC sheet.
        self.target = make_participant(
            self.encounter, kind="mook", name="Target",
            mook_combat_pool=2, mook_defense=1, faction="hostile",
        )

    def _attack_url(self):
        return reverse("combat:attack", kwargs={
            "pk": self.encounter.pk,
            "attacker_id": self.attacker.pk,
        })

    def test_attack_consumes_ammo(self):
        """A single shot decrements the ``ammo:N`` tag by 1."""
        self.client.force_login(self.gm)
        self.client.post(self._attack_url(), {
            "target_id": self.target.pk,
            "burst_mode": "single",
        })
        self.attacker.refresh_from_db()
        self.assertIn("ammo:4", self.attacker.conditions)

    def test_attack_rejects_when_out_of_ammo(self):
        """Empty mag flashes + redirects without rolling a single die."""
        self.attacker.conditions = ["ammo:0"]
        self.attacker.save(update_fields=["conditions"])
        self.client.force_login(self.gm)
        # Count attack rows before; expect zero new ones after.
        attack_rows_before = CombatLog.objects.filter(
            encounter=self.encounter, action_type="attack"
        ).count()
        self.client.post(self._attack_url(), {
            "target_id": self.target.pk,
            "burst_mode": "single",
        })
        attack_rows_after = CombatLog.objects.filter(
            encounter=self.encounter, action_type="attack"
        ).count()
        self.assertEqual(attack_rows_before, attack_rows_after)

    def test_attack_silently_downgrades_burst_when_insufficient(self):
        """5 ammo + medium burst (cost 10) downgrades to single fire.

        The attacker rolls — but only one round is consumed. A
        ``system`` log row notes the downgrade.
        """
        # Make weapon auto_capable so burst isn't downgraded due to
        # lack of capability — we want to hit the ammo branch.
        self.attacker.weapon_data = dict(self.attacker.weapon_data,
                                         auto_capable=True)
        self.attacker.save(update_fields=["weapon_data"])
        self.client.force_login(self.gm)
        self.client.post(self._attack_url(), {
            "target_id": self.target.pk,
            "burst_mode": "medium",
        })
        self.attacker.refresh_from_db()
        # Single-fire downgrade → 1 round consumed, mag now 4.
        self.assertIn("ammo:4", self.attacker.conditions)
        # System log row noting "Insufficient ammo".
        sys_rows = CombatLog.objects.filter(
            encounter=self.encounter, action_type="system",
        )
        self.assertTrue(any("Insufficient ammo" in r.message for r in sys_rows))

    def test_full_cover_blocks_attack(self):
        """Target with ``cover_state="full"`` produces a blocked outcome."""
        self.target.cover_state = "full"
        self.target.save(update_fields=["cover_state"])
        self.client.force_login(self.gm)
        self.client.post(self._attack_url(), {
            "target_id": self.target.pk,
            "burst_mode": "single",
        })
        attack_rows = CombatLog.objects.filter(
            encounter=self.encounter, action_type="attack",
        )
        self.assertTrue(attack_rows.exists())
        # The blocked-by-cover branch logs outcome="blocked_by_cover".
        outcomes = [r.data.get("outcome") for r in attack_rows]
        self.assertIn("blocked_by_cover", outcomes)

    def test_surprise_round_zeroes_defense(self):
        """Round 1 + surprise + non-immune target → defense computes to 0."""
        from combat.views import _compute_defense
        self.encounter.metadata = {"is_surprise_round": True}
        self.encounter.round_number = 1
        self.encounter.save(update_fields=["metadata", "round_number"])
        self.target.surprise_immune = False
        self.target.save(update_fields=["surprise_immune"])
        # Force-fetch a fresh participant because _compute_defense
        # reads the encounter via ``participant.encounter``.
        self.target.refresh_from_db()
        self.assertEqual(_compute_defense(self.target), 0)

    def test_surprise_round_skipped_after_round_1(self):
        """Round 2+ falls back to normal defense computation."""
        from combat.views import _compute_defense
        self.encounter.metadata = {"is_surprise_round": True}
        self.encounter.round_number = 2
        self.encounter.save(update_fields=["metadata", "round_number"])
        self.target.refresh_from_db()
        # mook_defense=1 falls through normally.
        self.assertEqual(_compute_defense(self.target), 1)

    def test_alert_target_immune_to_surprise(self):
        """``surprise_immune=True`` target keeps normal defense even round 1."""
        from combat.views import _compute_defense
        self.encounter.metadata = {"is_surprise_round": True}
        self.encounter.round_number = 1
        self.encounter.save(update_fields=["metadata", "round_number"])
        self.target.surprise_immune = True
        self.target.save(update_fields=["surprise_immune"])
        self.target.refresh_from_db()
        self.assertEqual(_compute_defense(self.target), 1)


# ---------------------------------------------------------------------------
# Permission gates — _gm_only + _gm_or_owner
# ---------------------------------------------------------------------------


class PermissionTests(TestCase):
    """Tests for the GM-only / GM-or-owner decorators."""

    def setUp(self):
        self.gm = make_user(is_superuser=True)
        self.player = make_user()
        self.other_player = make_user()
        self.client = Client()
        self.encounter = make_encounter(
            gm=self.gm, status="active", round_number=1,
        )
        self.char = make_character(owner=self.player)
        self.participant = make_participant(
            self.encounter, character=self.char, kind="character",
            name=self.char.name, faction="player",
        )
        self.encounter.active_participant_id = self.participant.pk
        self.encounter.initiative_order = [self.participant.pk]
        self.encounter.save()

    def test_gm_only_view_rejects_non_gm(self):
        """Non-superusers hit a 403 on encounter_create."""
        self.client.force_login(self.player)
        resp = self.client.post(
            reverse("combat:create"), {"title": "Should fail"},
        )
        self.assertEqual(resp.status_code, 403)

    def test_player_can_attack_with_own_character(self):
        """Owner can fire ``attack`` against their own participant.

        Pre-v0.15.5 surface: the ATTACK url is gated on
        ``_gm_or_owner("attacker_id")``. The owner of the underlying
        Character should pass the gate (302 redirect, not 403).
        """
        target = make_participant(
            self.encounter, kind="mook", name="Target",
            mook_combat_pool=2, mook_defense=1,
        )
        self.client.force_login(self.player)
        resp = self.client.post(
            reverse("combat:attack", kwargs={
                "pk": self.encounter.pk,
                "attacker_id": self.participant.pk,
            }),
            {"target_id": target.pk, "burst_mode": "single"},
        )
        # 302 — the owner gate passed (the action may still be a
        # noop, but the decorator didn't reject it).
        self.assertEqual(resp.status_code, 302)

    def test_player_cannot_attack_with_other_character(self):
        """Non-owner gets a 403 when targeting another player's row."""
        self.client.force_login(self.other_player)
        resp = self.client.post(
            reverse("combat:attack", kwargs={
                "pk": self.encounter.pk,
                "attacker_id": self.participant.pk,
            }),
            {"target_id": 1, "burst_mode": "single"},
        )
        self.assertEqual(resp.status_code, 403)

    def test_player_cannot_modify_npc_or_mook(self):
        """Players can't drive NPC / mook participants — no character FK."""
        mook = make_participant(
            self.encounter, kind="mook", name="Goon",
            mook_combat_pool=4,
        )
        self.client.force_login(self.player)
        resp = self.client.post(
            reverse("combat:roll_initiative", kwargs={
                "pk": self.encounter.pk,
                "participant_id": mook.pk,
            }),
        )
        self.assertEqual(resp.status_code, 403)


# ---------------------------------------------------------------------------
# Player-ready gate at start
# ---------------------------------------------------------------------------


class ReadyGateTests(TestCase):
    """Tests for the v0.15.24 player-ready gate at ``start_encounter``."""

    def setUp(self):
        self.gm = make_user(is_superuser=True)
        self.player = make_user()
        self.client = Client()
        self.encounter = make_encounter(gm=self.gm, status="setup")
        self.char = make_character(owner=self.player)
        self.participant = make_participant(
            self.encounter, character=self.char, kind="character",
            name=self.char.name, faction="player",
        )
        # Pre-roll initiative so the unrolled-count gate doesn't fire
        # before the ready-gate gate gets a chance.
        self.participant.initiative_score = 8
        self.participant.initiative_roll = 4
        self.participant.save(update_fields=[
            "initiative_score", "initiative_roll",
        ])

    def test_start_rejects_when_not_all_ready(self):
        """An unready Character participant blocks ``start_encounter``.

        Pre-v0.15.35 the start-gate's JSONField ``__contains`` query
        crashes on SQLite (the lookup requires the JSON1 extension and
        Django's SQLite backend emits ``NotSupportedError``). To pin
        the *intent* of the gate without depending on backend support
        we test :func:`_participants_needing_ready` + :func:`_is_ready`
        directly — same predicate the view body uses, just without the
        ORM ``__contains`` round-trip.
        """
        from combat.views import _is_ready, _participants_needing_ready
        # No "ready" tag set on participant.conditions.
        unready = [
            p for p in _participants_needing_ready(self.encounter)
            if not _is_ready(p)
        ]
        # Exactly one Character participant, not yet readied → gate blocks.
        self.assertEqual(len(unready), 1)
        self.assertEqual(unready[0].pk, self.participant.pk)

    def test_force_start_overrides_ready(self):
        """``force_start=1`` skips the gate even with unready players.

        With FORCE START set, the unready-name query inside
        ``start_encounter`` is short-circuited entirely — no SQLite
        ``__contains`` lookup runs and the encounter transitions
        cleanly to active.
        """
        self.client.force_login(self.gm)
        self.client.post(
            reverse("combat:start", kwargs={"pk": self.encounter.pk}),
            {"force_start": "1"},
        )
        self.encounter.refresh_from_db()
        self.assertEqual(self.encounter.status, "active")


# ---------------------------------------------------------------------------
# Burn tick — GM-driven manual damage application
# ---------------------------------------------------------------------------


class BurnTickTests(TestCase):
    """Tests for the v0.15.30 GM-driven burn tick view."""

    def setUp(self):
        self.gm = make_user(is_superuser=True)
        self.client = Client()
        self.encounter = make_encounter(
            gm=self.gm, status="active", round_number=2,
        )
        self.target = make_participant(
            self.encounter, kind="mook", name="Burner",
            mook_combat_pool=4, mook_defense=2,
            health_max=7, conditions=["burning"],
        )

    def test_tick_burn_applies_damage(self):
        """``tick_burn`` with dice=2 type=L applies 2 lethal damage."""
        self.client.force_login(self.gm)
        self.client.post(
            reverse("combat:tick_burn", kwargs={
                "pk": self.encounter.pk,
                "participant_id": self.target.pk,
            }),
            {"burn_dice": "2", "damage_type": "L"},
        )
        self.target.refresh_from_db()
        self.assertEqual(self.target.health_lethal, 2)

    def test_tick_burn_skip_zero_dice(self):
        """``burn_dice=0`` logs a system row but applies no damage."""
        self.client.force_login(self.gm)
        self.client.post(
            reverse("combat:tick_burn", kwargs={
                "pk": self.encounter.pk,
                "participant_id": self.target.pk,
            }),
            {"burn_dice": "0", "damage_type": "L"},
        )
        self.target.refresh_from_db()
        self.assertEqual(self.target.health_lethal, 0)
        # The row still gets logged for timeline visibility.
        burn_rows = CombatLog.objects.filter(
            encounter=self.encounter, action_type="burn_tick",
        )
        self.assertTrue(burn_rows.exists())


# ---------------------------------------------------------------------------
# Knockdown — auto-trigger on shotgun hits + already-prone skip
# ---------------------------------------------------------------------------


class KnockdownTests(TestCase):
    """Tests for the v0.15.26 knockdown auto-trigger."""

    def setUp(self):
        self.gm = make_user(is_superuser=True)
        self.client = Client()
        self.encounter = make_encounter(
            gm=self.gm, status="active", round_number=1,
        )
        # Attacker is a high-pool mook so the hit is virtually
        # guaranteed against a low-defense target.
        self.attacker = make_participant(
            self.encounter, kind="mook", name="Shooter",
            mook_combat_pool=20, mook_defense=2,
            weapon_name="Shotgun",
            weapon_data={
                "name": "Shotgun", "category": "firearm",
                "damage": "4L", "again": 10,
                "knockdown_capable": True,
                "auto_capable": False,
            },
        )
        self.encounter.active_participant_id = self.attacker.pk
        self.encounter.initiative_order = [self.attacker.pk]
        self.encounter.save()

    def test_shotgun_hit_triggers_knockdown_roll(self):
        """A landed knockdown_capable hit fires the knockdown contest.

        With attacker pool 20 vs target defense 2, the attack lands.
        We patch the resistance roll to fail (returns 0 successes) so
        the target should drop prone.
        """
        target = make_participant(
            self.encounter, kind="mook", name="Standee",
            mook_combat_pool=2, mook_defense=1, health_max=7,
        )
        self.client.force_login(self.gm)
        # Patch _roll_pool only for the resistance roll. The attacker
        # roll has to land normally; the knockdown contest call
        # (_roll_pool against the target's resistance pool) needs to
        # return 0 successes. Simplest: patch with a stateful side
        # effect that returns a high count first (attack lands), then
        # 0 (resistance fails).
        from combat import views as combat_views
        orig_roll = combat_views._roll_pool
        call_count = {"n": 0}
        def fake_roll(n, again_threshold=10):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # Attacker roll — land successes.
                return 10, [{"face": 10, "kind": "base", "from_index": None,
                             "success": True, "exploded": True}]
            # Subsequent calls (resistance) — fail.
            return 0, []
        with patch("combat.views._roll_pool", side_effect=fake_roll):
            self.client.post(
                reverse("combat:attack", kwargs={
                    "pk": self.encounter.pk,
                    "attacker_id": self.attacker.pk,
                }),
                {"target_id": target.pk, "burst_mode": "single"},
            )
        # A knockdown row should have been written.
        knockdown_rows = CombatLog.objects.filter(
            encounter=self.encounter, action_type="knockdown",
        )
        self.assertTrue(knockdown_rows.exists())

    def test_already_prone_target_skips_knockdown(self):
        """Already-prone targets short-circuit the knockdown contest."""
        target = make_participant(
            self.encounter, kind="mook", name="Floored",
            mook_combat_pool=2, mook_defense=1, health_max=7,
            conditions=["prone"],
        )
        self.client.force_login(self.gm)
        self.client.post(
            reverse("combat:attack", kwargs={
                "pk": self.encounter.pk,
                "attacker_id": self.attacker.pk,
            }),
            {"target_id": target.pk, "burst_mode": "single"},
        )
        # No knockdown row written.
        knockdown_rows = CombatLog.objects.filter(
            encounter=self.encounter, action_type="knockdown",
        )
        self.assertFalse(knockdown_rows.exists())


# ---------------------------------------------------------------------------
# Grenades — inventory + EMP immunity + scatter
# ---------------------------------------------------------------------------


class GrenadeTests(TestCase):
    """Tests for the v0.15.29 grenade inventory + throw resolver."""

    def setUp(self):
        self.gm = make_user(is_superuser=True)
        self.client = Client()
        self.encounter = make_encounter(
            gm=self.gm, status="active", round_number=1,
        )
        # Throwers need character/npc FK so the resolver can compute
        # Dex + Athletics. Use a Character so the GM can drive it
        # directly.
        self.player = make_user()
        self.char = make_character(owner=self.player, character_class="soldier")
        self.thrower = make_participant(
            self.encounter, character=self.char, kind="character",
            name=self.char.name, faction="player",
            conditions=["grenades:frag:3", "grenades:emp:2"],
        )
        self.encounter.active_participant_id = self.thrower.pk
        self.encounter.initiative_order = [self.thrower.pk]
        self.encounter.save()

    def test_throw_grenade_decrements_inventory(self):
        """A successful throw drops one grenade from the inventory."""
        target = make_participant(
            self.encounter, kind="mook", name="Boom",
            mook_combat_pool=2, mook_defense=1, health_max=7,
        )
        self.client.force_login(self.gm)
        # Patch the throw roll to land at least one success so the
        # scatter branch doesn't fire.
        with patch("combat.views._roll_pool",
                   return_value=(3, [{"face": 10, "kind": "base",
                                      "from_index": None, "success": True,
                                      "exploded": True}])):
            self.client.post(
                reverse("combat:throw_grenade", kwargs={
                    "pk": self.encounter.pk,
                    "participant_id": self.thrower.pk,
                }),
                {
                    "grenade_type": "frag",
                    "target_ids": [str(target.pk)],
                },
            )
        self.thrower.refresh_from_db()
        # Frag inventory should be 2 now (was 3).
        self.assertIn("grenades:frag:2", self.thrower.conditions)

    def test_grenade_emp_immune_for_non_ai(self):
        """A non-AI biological target shrugs off the EMP effect."""
        # Soldier-class mook has no class info → biological → immune.
        target = make_participant(
            self.encounter, kind="mook", name="Biological",
            mook_combat_pool=2, mook_defense=1, health_max=7,
        )
        self.client.force_login(self.gm)
        with patch("combat.views._roll_pool",
                   return_value=(3, [{"face": 10, "kind": "base",
                                      "from_index": None, "success": True,
                                      "exploded": True}])):
            self.client.post(
                reverse("combat:throw_grenade", kwargs={
                    "pk": self.encounter.pk,
                    "participant_id": self.thrower.pk,
                }),
                {
                    "grenade_type": "emp",
                    "target_ids": [str(target.pk)],
                },
            )
        target.refresh_from_db()
        # No emp_disabled tag should have landed on the biological mook.
        self.assertNotIn("emp_disabled", target.conditions)
        # An "immune to EMP" system row should have been written.
        sys_rows = CombatLog.objects.filter(
            encounter=self.encounter, action_type="system",
        )
        self.assertTrue(any("immune to EMP" in r.message for r in sys_rows))

    def test_grenade_scatter_on_zero_successes(self):
        """A 0-success throw fires the scatter branch and consumes 1 grenade."""
        target = make_participant(
            self.encounter, kind="mook", name="Lucky",
            mook_combat_pool=2, mook_defense=1, health_max=7,
        )
        self.client.force_login(self.gm)
        # Force the roll to land 0 successes → scatter.
        with patch("combat.views._roll_pool", return_value=(0, [])):
            self.client.post(
                reverse("combat:throw_grenade", kwargs={
                    "pk": self.encounter.pk,
                    "participant_id": self.thrower.pk,
                }),
                {
                    "grenade_type": "frag",
                    "target_ids": [str(target.pk)],
                },
            )
        # A grenade_scatter log row should exist; inventory drops to 2.
        scatter_rows = CombatLog.objects.filter(
            encounter=self.encounter, action_type="grenade_scatter",
        )
        self.assertTrue(scatter_rows.exists())
        target.refresh_from_db()
        # Target should not have taken damage.
        self.assertEqual(target.health_lethal, 0)
        self.thrower.refresh_from_db()
        # Frag count decremented from 3 → 2.
        self.assertIn("grenades:frag:2", self.thrower.conditions)
