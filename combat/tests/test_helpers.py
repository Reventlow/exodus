"""Pure-helper tests for combat/views.py.

Targets the 20+ side-effect-free helpers that drive the rules math:
dice rolling, damage application, wound penalties, Gun Fu distribution,
weapon parsing, condition tags, and the dice-payload renderer.

Most classes inherit from :class:`SimpleTestCase` (no DB roundtrip,
fast). The damage / wound-penalty groups need DB-backed Participant
rows so they use :class:`TestCase` and lean on the helpers in
``combat/tests/factories.py`` for setup.
"""

from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from combat import views as combat_views
from combat.views import (
    _apply_damage,
    _clamp_again_local,
    _condition_attack_modifier,
    _distribute_gun_fu,
    _grenade_slug,
    _normalize_dice_payload,
    _parse_aim_tag,
    _parse_ammo_tag,
    _parse_grenade_tag,
    _parse_weapon_damage,
    _roll_pool,
    _wound_penalty,
)
from combat.tests.factories import (
    attach_merit,
    make_character,
    make_encounter,
    make_merit,
    make_participant,
    make_user,
)


# ---------------------------------------------------------------------------
# _roll_pool — dice rolling, X-again explosions, threshold handling
# ---------------------------------------------------------------------------


class RollPoolTests(SimpleTestCase):
    """Tests for :func:`combat.views._roll_pool` (no DB)."""

    def test_zero_dice_returns_empty(self):
        """Zero or negative dice returns ``(0, [])`` immediately."""
        successes, dice = _roll_pool(0)
        self.assertEqual(successes, 0)
        self.assertEqual(dice, [])

    def test_negative_dice_returns_empty(self):
        """Negative pool sizes collapse to the empty result, not an error."""
        successes, dice = _roll_pool(-5)
        self.assertEqual(successes, 0)
        self.assertEqual(dice, [])

    def test_single_die_face_in_range(self):
        """Every face produced by the roll is in [1, 10]."""
        _, dice = _roll_pool(1)
        self.assertEqual(len(dice), 1)
        self.assertTrue(1 <= dice[0]["face"] <= 10)

    def test_dice_count_increases_with_pool(self):
        """A 100-die pool always yields at least 100 dice entries.

        Explosion mechanics can add more, never fewer — base dice are
        appended unconditionally.
        """
        _, dice = _roll_pool(100)
        self.assertGreaterEqual(len(dice), 100)

    def test_explosion_chain_capped(self):
        """All-10 explosion chain is capped at 5 levels per starting die.

        We patch the d10 source to always return 10. With a single
        starting die, the chain should produce exactly 1 base + 5
        explodes = 6 entries (cap = 5).
        """
        with patch("combat.views._roll_d10", return_value=10):
            successes, dice = _roll_pool(1)
        # Cap is 5 explode-levels → 1 base + 5 explodes = 6 dice
        self.assertEqual(len(dice), 6)
        self.assertEqual(dice[0]["kind"], "base")
        for d in dice[1:]:
            self.assertEqual(d["kind"], "explode")
        # All faces are 10 → all successes.
        self.assertEqual(successes, 6)

    def test_again_threshold_8_more_explosions_than_10(self):
        """Threshold 8 yields more total dice than threshold 10.

        Loose statistical bound — over a 500-die pool the 8-again pool
        explodes on three faces (8/9/10) vs 10-again's single face, so
        we expect ~3x the trigger rate. Total dice are dominated by the
        base count (500), so we assert a modest 1.1x lower bound on
        the total — comfortably above noise but well below the
        theoretical mean. Variance shouldn't make this flaky.
        """
        _, dice_8 = _roll_pool(500, again_threshold=8)
        _, dice_10 = _roll_pool(500, again_threshold=10)
        self.assertGreater(len(dice_8), int(len(dice_10) * 1.1))

    def test_dice_dict_shape(self):
        """Every dice entry has the canonical key set."""
        _, dice = _roll_pool(20)
        required_keys = {"face", "kind", "from_index", "success", "exploded"}
        for d in dice:
            self.assertEqual(set(d.keys()), required_keys)
            self.assertIn(d["kind"], ("base", "explode"))
            self.assertIsInstance(d["success"], bool)
            self.assertIsInstance(d["exploded"], bool)


# ---------------------------------------------------------------------------
# _apply_damage — WoD 2.0 track upgrade ladder (B → L → A)
# ---------------------------------------------------------------------------


class DamageApplicationTests(TestCase):
    """Tests for :func:`combat.views._apply_damage` (DB-backed)."""

    def setUp(self):
        gm = make_user(is_superuser=True)
        encounter = make_encounter(gm=gm)
        # Bare mook participant — no Character / NPC FK needed for the
        # damage math. ``health_max=7`` is the WoD 2.0 default.
        self.participant = make_participant(
            encounter, kind="mook", name="Dummy",
            mook_combat_pool=5, health_max=7,
        )

    def test_apply_bashing_within_track(self):
        """3 bashing on an empty track fills 3 bashing boxes."""
        applied, upgrades, overflow = _apply_damage(self.participant, 3, "B")
        self.participant.refresh_from_db()
        self.assertEqual(self.participant.health_bashing, 3)
        self.assertEqual(self.participant.health_lethal, 0)
        self.assertEqual(self.participant.health_aggravated, 0)
        self.assertEqual(applied, 3)
        self.assertEqual(upgrades, 0)
        self.assertEqual(overflow, 0)

    def test_apply_lethal_displaces_bashing(self):
        """Lethal overflow on a full bashing track upgrades B → L.

        Pre-state: 7 bashing (track full).
        Incoming: 3 lethal.
        Expected: each L overflow upgrades a B box, so b=4, l=3.
        """
        self.participant.health_bashing = 7
        self.participant.save(update_fields=["health_bashing"])
        applied, upgrades, overflow = _apply_damage(self.participant, 3, "L")
        self.participant.refresh_from_db()
        self.assertEqual(self.participant.health_bashing, 4)
        self.assertEqual(self.participant.health_lethal, 3)
        self.assertEqual(applied, 0)   # no empty boxes
        self.assertEqual(upgrades, 3)
        self.assertEqual(overflow, 0)

    def test_apply_aggravated_displaces_both(self):
        """Aggravated overflow upgrades B then L.

        Pre-state: b=3, l=4 (track full at 7 boxes).
        Incoming: 2 aggravated.
        Expected: A upgrades B first → b=2, l=4, a=1; then second A
        keeps eating B → b=1, l=4, a=2.
        """
        self.participant.health_bashing = 3
        self.participant.health_lethal = 4
        self.participant.save(update_fields=[
            "health_bashing", "health_lethal",
        ])
        applied, upgrades, overflow = _apply_damage(self.participant, 2, "A")
        self.participant.refresh_from_db()
        self.assertEqual(self.participant.health_bashing, 1)
        self.assertEqual(self.participant.health_lethal, 4)
        self.assertEqual(self.participant.health_aggravated, 2)
        self.assertEqual(upgrades, 2)
        self.assertEqual(overflow, 0)

    def test_overflow_capped_at_health_max(self):
        """Total damage on a full track never exceeds ``health_max``."""
        # Fill track entirely with lethal then dump aggravated overflow.
        self.participant.health_lethal = 7
        self.participant.save(update_fields=["health_lethal"])
        _apply_damage(self.participant, 100, "A")
        self.participant.refresh_from_db()
        total = (
            self.participant.health_bashing
            + self.participant.health_lethal
            + self.participant.health_aggravated
        )
        self.assertLessEqual(total, self.participant.health_max)

    def test_track_upgrades_logged(self):
        """Return shape is ``(applied, upgrades, overflow)`` ints."""
        result = _apply_damage(self.participant, 2, "B")
        self.assertEqual(len(result), 3)
        for v in result:
            self.assertIsInstance(v, int)


# ---------------------------------------------------------------------------
# _wound_penalty — WoD 2.0 wound penalty + Pain Tolerance / IPT merits
# ---------------------------------------------------------------------------


class WoundPenaltyTests(TestCase):
    """Tests for :func:`combat.views._wound_penalty` (DB-backed)."""

    def setUp(self):
        self.player = make_user()
        self.gm = make_user(is_superuser=True)
        self.encounter = make_encounter(gm=self.gm)
        self.character = make_character(owner=self.player, name="Wound Test")
        # All character merits link via the canonical M2M
        # CharacterMerit through-table; these merits exist in the
        # MeritDefinition catalogue at game-runtime, so we seed them
        # at test time for the ones we care about.
        self.pain_tolerance = make_merit("Pain Tolerance")
        self.ipt = make_merit("Increased Pain Threshold")

    def _participant_for(self, b=0, l=0, a=0):
        """Helper: return a fresh Character participant with the given track."""
        return make_participant(
            self.encounter, character=self.character, kind="character",
            name=self.character.name,
            health_max=7, health_bashing=b, health_lethal=l, health_aggravated=a,
        )

    def test_no_penalty_below_threshold(self):
        """4 damage on a 7-box track is below the rightmost-three zone."""
        p = self._participant_for(b=4)
        self.assertEqual(_wound_penalty(p), 0)

    def test_minus_one_at_three_from_end(self):
        """5 damage on 7 → -1 (first wound penalty box)."""
        p = self._participant_for(b=5)
        self.assertEqual(_wound_penalty(p), -1)

    def test_minus_two_at_two_from_end(self):
        """6 damage on 7 → -2."""
        p = self._participant_for(b=6)
        self.assertEqual(_wound_penalty(p), -2)

    def test_minus_three_when_track_full(self):
        """7 damage on 7 → -3 (rightmost box filled, incapacitated)."""
        p = self._participant_for(b=7)
        self.assertEqual(_wound_penalty(p), -3)

    def test_pain_tolerance_zeroes_penalty(self):
        """Pain Tolerance short-circuits to 0 regardless of damage."""
        p = self._participant_for(b=7)
        attach_merit(self.character, self.pain_tolerance, rating=5)
        self.assertEqual(_wound_penalty(p), 0)

    def test_increased_pain_threshold_reduces_one(self):
        """IPT reduces the penalty by 1 toward zero (-2 → -1)."""
        p = self._participant_for(b=6)
        attach_merit(self.character, self.ipt, rating=3)
        self.assertEqual(_wound_penalty(p), -1)

    def test_pain_tolerance_overrides_ipt(self):
        """Pain Tolerance wins when both merits are present."""
        p = self._participant_for(b=6)
        attach_merit(self.character, self.pain_tolerance, rating=5)
        attach_merit(self.character, self.ipt, rating=3)
        self.assertEqual(_wound_penalty(p), 0)

    def test_mook_unaffected(self):
        """Mooks have no merit lookups — raw penalty applies."""
        mook = make_participant(
            self.encounter, kind="mook", name="Goon",
            mook_combat_pool=5, health_max=7, health_bashing=7,
        )
        self.assertEqual(_wound_penalty(mook), -3)


# ---------------------------------------------------------------------------
# _distribute_gun_fu — split N auto-successes across M targets
# ---------------------------------------------------------------------------


class GunFuDistributionTests(SimpleTestCase):
    """Tests for :func:`combat.views._distribute_gun_fu` (no DB)."""

    def test_5_across_4_targets(self):
        """5 uses, 4 targets → [2, 1, 1, 1] (extra lands on slot 0)."""
        self.assertEqual(_distribute_gun_fu(5, 4), [2, 1, 1, 1])

    def test_5_across_2_targets(self):
        """5 uses, 2 targets → [3, 2]."""
        self.assertEqual(_distribute_gun_fu(5, 2), [3, 2])

    def test_3_across_1_target(self):
        """All 3 uses land on the single target."""
        self.assertEqual(_distribute_gun_fu(3, 1), [3])

    def test_0_uses_returns_zeros(self):
        """Zero uses → vector of zeros sized to target count."""
        self.assertEqual(_distribute_gun_fu(0, 4), [0, 0, 0, 0])

    def test_more_uses_than_targets_distributes_extra_to_first(self):
        """7 uses across 4 targets: base=1, extra=3 → [2, 2, 2, 1]."""
        self.assertEqual(_distribute_gun_fu(7, 4), [2, 2, 2, 1])

    def test_zero_targets_returns_empty(self):
        """Zero targets always returns ``[]`` (no slot to land on)."""
        self.assertEqual(_distribute_gun_fu(5, 0), [])


# ---------------------------------------------------------------------------
# Weapon parsing + clamping helpers
# ---------------------------------------------------------------------------


class WeaponParsingTests(SimpleTestCase):
    """Tests for :func:`combat.views._parse_weapon_damage` and clampers."""

    def test_simple_damage_parses_close_only(self):
        """``"2L"`` → close=(2, "L"), other bands None."""
        parsed = _parse_weapon_damage("2L")
        self.assertEqual(parsed["close"], (2, "L"))
        self.assertIsNone(parsed["medium"])
        self.assertIsNone(parsed["long"])

    def test_two_band_damage(self):
        """``"4L close / 2L long"`` parses both bands."""
        parsed = _parse_weapon_damage("4L close / 2L long")
        self.assertEqual(parsed["close"], (4, "L"))
        self.assertEqual(parsed["long"], (2, "L"))
        self.assertIsNone(parsed["medium"])

    def test_three_band_damage(self):
        """``"2L close / 2L medium / 1L long"`` parses all three bands."""
        parsed = _parse_weapon_damage("2L close / 2L medium / 1L long")
        self.assertEqual(parsed["close"], (2, "L"))
        self.assertEqual(parsed["medium"], (2, "L"))
        self.assertEqual(parsed["long"], (1, "L"))

    def test_parens_stripped(self):
        """``"5L (both barrels)"`` parses as single-band 5L."""
        parsed = _parse_weapon_damage("5L (both barrels)")
        self.assertEqual(parsed["close"], (5, "L"))
        self.assertIsNone(parsed["long"])
        self.assertIsNone(parsed["medium"])

    def test_empty_string(self):
        """Empty input collapses to ``(0, "L")`` close band."""
        parsed = _parse_weapon_damage("")
        self.assertEqual(parsed["close"], (0, "L"))
        self.assertIsNone(parsed["medium"])
        self.assertIsNone(parsed["long"])

    def test_clamp_again_threshold(self):
        """Clamps explosion threshold to {8, 9, 10}; bad input → 10."""
        self.assertEqual(_clamp_again_local(8), 8)
        self.assertEqual(_clamp_again_local(9), 9)
        self.assertEqual(_clamp_again_local(10), 10)
        # Garbage / out-of-range collapse to 10.
        self.assertEqual(_clamp_again_local(7), 10)
        self.assertEqual(_clamp_again_local(11), 10)
        self.assertEqual(_clamp_again_local(None), 10)
        self.assertEqual(_clamp_again_local("bad"), 10)


# ---------------------------------------------------------------------------
# Condition tag parsers (aim / ammo / grenade)
# ---------------------------------------------------------------------------


class ConditionTagTests(SimpleTestCase):
    """Tests for the condition-tag parser helpers (no DB)."""

    def test_parse_aim_tag(self):
        """``aiming_at:42:2`` → ``(42, 2)``; bad input → None."""
        self.assertEqual(_parse_aim_tag("aiming_at:42:2"), (42, 2))
        # Wrong prefix.
        self.assertIsNone(_parse_aim_tag("foo:42:2"))
        # Wrong arity.
        self.assertIsNone(_parse_aim_tag("aiming_at:42"))
        # Non-string.
        self.assertIsNone(_parse_aim_tag(None))
        self.assertIsNone(_parse_aim_tag(42))

    def test_parse_ammo_tag(self):
        """``ammo:7`` → 7; bad input → None."""
        self.assertEqual(_parse_ammo_tag("ammo:7"), 7)
        self.assertEqual(_parse_ammo_tag("ammo:0"), 0)
        # Wrong prefix.
        self.assertIsNone(_parse_ammo_tag("foo"))
        # Non-string.
        self.assertIsNone(_parse_ammo_tag(None))

    def test_parse_grenade_tag(self):
        """``grenades:frag:3`` → ``("frag", 3)``."""
        self.assertEqual(_parse_grenade_tag("grenades:frag:3"), ("frag", 3))
        # Bad shape returns (None, 0).
        self.assertEqual(_parse_grenade_tag("grenades:frag"), (None, 0))
        self.assertEqual(_parse_grenade_tag("foo"), (None, 0))
        self.assertEqual(_parse_grenade_tag(None), (None, 0))

    def test_grenade_slug(self):
        """First-word lowercase token; multi-word names slug cleanly."""
        self.assertEqual(_grenade_slug("Frag Grenade"), "frag")
        self.assertEqual(_grenade_slug("Stun Grenade (Flashbang)"), "stun")
        self.assertEqual(_grenade_slug("EMP Grenade"), "emp")
        # Empty / None safe paths.
        self.assertEqual(_grenade_slug(""), "")
        self.assertEqual(_grenade_slug(None), "")


# ---------------------------------------------------------------------------
# _normalize_dice_payload — backward-compat for the dice renderer
# ---------------------------------------------------------------------------


class DiceRendererTests(SimpleTestCase):
    """Tests for :func:`combat.views._normalize_dice_payload` (no DB)."""

    def test_normalize_dice_payload_legacy_int_list(self):
        """Pre-v0.15.18 flat int lists hydrate into structured dicts.

        Every entry gets ``kind="base"``; ``exploded`` is True iff the
        face was 10 (legacy 10-again back-fill).
        """
        out = _normalize_dice_payload([10, 7, 8])
        self.assertEqual(len(out), 3)
        self.assertEqual(out[0]["face"], 10)
        self.assertTrue(out[0]["exploded"])
        self.assertEqual(out[1]["face"], 7)
        self.assertFalse(out[1]["exploded"])
        # 8 is a success but not a trigger face under legacy 10-again.
        self.assertTrue(out[2]["success"])
        self.assertFalse(out[2]["exploded"])
        for d in out:
            self.assertEqual(d["kind"], "base")

    def test_normalize_dice_payload_structured_passthrough(self):
        """Already-structured input round-trips with all keys preserved."""
        original = [
            {"face": 9, "kind": "base", "from_index": None,
             "success": True, "exploded": True},
        ]
        out = _normalize_dice_payload(original)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["face"], 9)
        self.assertTrue(out[0]["exploded"])

    def test_normalize_dice_payload_handles_none(self):
        """None / non-list input collapses to ``[]``."""
        self.assertEqual(_normalize_dice_payload(None), [])

    def test_normalize_dice_payload_handles_garbage(self):
        """Strings / other non-list types also collapse to ``[]``."""
        self.assertEqual(_normalize_dice_payload("not a list"), [])
        self.assertEqual(_normalize_dice_payload(42), [])


# ---------------------------------------------------------------------------
# _condition_attack_modifier — additive condition mods, floored at -10
# ---------------------------------------------------------------------------


class ConditionModifierTests(TestCase):
    """Tests for :func:`combat.views._condition_attack_modifier`."""

    def setUp(self):
        gm = make_user(is_superuser=True)
        self.encounter = make_encounter(gm=gm)

    def test_no_conditions_returns_zero(self):
        """Empty conditions list yields 0 modifier."""
        p = make_participant(
            self.encounter, kind="mook", name="Clean", mook_combat_pool=5,
        )
        self.assertEqual(_condition_attack_modifier(p), 0)

    def test_stunned_subtracts_two(self):
        """``stunned`` carries -2 attack modifier."""
        p = make_participant(
            self.encounter, kind="mook", name="Stunned",
            mook_combat_pool=5, conditions=["stunned"],
        )
        self.assertEqual(_condition_attack_modifier(p), -2)
