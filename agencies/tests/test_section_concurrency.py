"""Regression tests for the multi-player concurrency fix on agency / base
section endpoints.

The bug being guarded against (the so-called "Bifrost bug"):

    The legacy per-base ``PUT`` handler silently dropped concurrent writes
    via an ``existing.issubset(proposed)`` guard. Two players adding
    different items to the same base's ``merits`` / ``facilities`` /
    ``equipment`` would race; the second player's addition vanished with
    no error returned to the client.

The backend fix introduced per-section ``PATCH`` endpoints with optimistic
concurrency control via the ``If-Match`` header and a per-section /
per-base monotonic version counter. These tests prove:

1. Concurrent writes resolve to exactly one 200 + one 409 — no silent drop.
2. The new section endpoints honour the documented contract (200 / 409 /
   400 / 403 / 404 shapes, ETag echoing, header parsing, alias acceptance).
3. The legacy ``PUT`` shims still work for backwards compatibility.
4. Permissions: admin-only sections gate non-admins, players can ADD but
   not REMOVE items from a base they belong to.
"""

import json
import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

import requests
from django.contrib.auth.models import User
from django.db import connection
from django.test import Client, LiveServerTestCase, TestCase

from agencies.models import Agency, Base
from characters.models import Character


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(username, *, is_superuser=False, password="testpass123"):
    """Create an active user with a known password."""
    return User.objects.create_user(
        username=username,
        password=password,
        is_superuser=is_superuser,
        is_staff=is_superuser,
        is_active=True,
    )


def _make_player_member_setup(agency, user, *, character_name="Agent X"):
    """Wire up ``user`` as a member of ``agency`` for membership checks.

    Mirrors ``_user_belongs_to_player_agency`` in views.py: the user must
    own a Character that is assigned to a workspace slot on one of the
    agency's bases.
    """
    char = Character.objects.create(owner=user, name=character_name)
    base = agency.bases.first()
    base.workspaces = [
        {"level": 1, "assignedType": "character", "assignedTo": char.id},
    ]
    base.save(update_fields=["workspaces"])
    return char


# ---------------------------------------------------------------------------
# Plain Client tests — no need for true HTTP concurrency.
# ---------------------------------------------------------------------------


class AgencySectionPatchTests(TestCase):
    """Behaviour of the agency-level ``/section/<key>/`` PATCH endpoints."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = _make_user("admin1", is_superuser=True)
        cls.player = _make_user("player1")
        cls.outsider = _make_user("outsider1")
        cls.agency = Agency.objects.create(
            name="Test Agency",
            is_player_agency=True,
            notes="initial notes",
            merits=[{"name": "Old Merit", "value": 1}],
        )
        cls.base = Base.objects.create(
            agency=cls.agency, name="HQ", location_type="safe_house",
        )
        # Make ``cls.player`` a member of cls.agency.
        _make_player_member_setup(cls.agency, cls.player)

    def setUp(self):
        self.client = Client()

    # ------------------------------------------------------------------
    # 200 path — version bump + ETag header.
    # ------------------------------------------------------------------

    def test_patch_with_correct_if_match_returns_200_and_bumps_version(self):
        self.client.login(username="admin1", password="testpass123")
        url = f"/api/agencies/{self.agency.id}/section/notes/"
        resp = self.client.patch(
            url,
            data=json.dumps({"notes": "fresh notes"}),
            content_type="application/json",
            HTTP_IF_MATCH="0",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["notes"], "fresh notes")
        self.assertEqual(body["version"], 1)
        self.assertEqual(resp["ETag"], "1")

        self.agency.refresh_from_db()
        self.assertEqual(self.agency.notes, "fresh notes")
        self.assertEqual(self.agency.section_versions.get("notes"), 1)

    def test_patch_without_if_match_force_writes_and_still_bumps_version(self):
        # Seed a non-zero starting version so we can prove we don't reset it.
        self.agency.section_versions = {"notes": 5}
        self.agency.save(update_fields=["section_versions"])

        self.client.login(username="admin1", password="testpass123")
        url = f"/api/agencies/{self.agency.id}/section/notes/"
        resp = self.client.patch(
            url,
            data=json.dumps({"notes": "force-written"}),
            content_type="application/json",
            # no If-Match header
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["version"], 6)
        self.assertEqual(resp["ETag"], "6")

    # ------------------------------------------------------------------
    # 409 path — stale write.
    # ------------------------------------------------------------------

    def test_patch_with_stale_if_match_returns_409_and_no_db_change(self):
        self.client.login(username="admin1", password="testpass123")
        # First, seed version=3 directly so we can pretend a stale client has 1.
        self.agency.section_versions = {"notes": 3}
        self.agency.notes = "current canonical"
        self.agency.save(update_fields=["section_versions", "notes"])

        url = f"/api/agencies/{self.agency.id}/section/notes/"
        resp = self.client.patch(
            url,
            data=json.dumps({"notes": "stale write"}),
            content_type="application/json",
            HTTP_IF_MATCH="1",
        )
        self.assertEqual(resp.status_code, 409)
        body = resp.json()
        self.assertIn("error", body)
        self.assertEqual(body["current_version"], 3)
        self.assertEqual(body["current_value"], "current canonical")

        self.agency.refresh_from_db()
        self.assertEqual(self.agency.notes, "current canonical")
        self.assertEqual(self.agency.section_versions.get("notes"), 3)

    # ------------------------------------------------------------------
    # If-Match parsing — bad shapes and weak/strong wrappers.
    # ------------------------------------------------------------------

    def test_patch_with_malformed_if_match_returns_400(self):
        self.client.login(username="admin1", password="testpass123")
        url = f"/api/agencies/{self.agency.id}/section/notes/"
        resp = self.client.patch(
            url,
            data=json.dumps({"notes": "x"}),
            content_type="application/json",
            HTTP_IF_MATCH="not-a-number",
        )
        self.assertEqual(resp.status_code, 400)

    def test_patch_accepts_quoted_if_match(self):
        self.client.login(username="admin1", password="testpass123")
        url = f"/api/agencies/{self.agency.id}/section/notes/"
        resp = self.client.patch(
            url,
            data=json.dumps({"notes": "quoted"}),
            content_type="application/json",
            HTTP_IF_MATCH='"0"',
        )
        self.assertEqual(resp.status_code, 200)

    def test_patch_accepts_weak_etag_if_match(self):
        self.client.login(username="admin1", password="testpass123")
        url = f"/api/agencies/{self.agency.id}/section/notes/"
        resp = self.client.patch(
            url,
            data=json.dumps({"notes": "weak"}),
            content_type="application/json",
            HTTP_IF_MATCH='W/"0"',
        )
        self.assertEqual(resp.status_code, 200)

    # ------------------------------------------------------------------
    # Per-section isolation — writing notes must not bump merits version.
    # ------------------------------------------------------------------

    def test_section_versions_are_independent_per_key(self):
        self.client.login(username="admin1", password="testpass123")

        notes_url = f"/api/agencies/{self.agency.id}/section/notes/"
        self.client.patch(
            notes_url,
            data=json.dumps({"notes": "a"}),
            content_type="application/json",
            HTTP_IF_MATCH="0",
        )
        self.agency.refresh_from_db()
        self.assertEqual(self.agency.section_versions.get("notes"), 1)
        self.assertNotIn("merits", self.agency.section_versions)

        merits_url = f"/api/agencies/{self.agency.id}/section/merits/"
        resp = self.client.patch(
            merits_url,
            data=json.dumps({"merits": [{"name": "New", "value": 2}]}),
            content_type="application/json",
            HTTP_IF_MATCH="0",
        )
        self.assertEqual(resp.status_code, 200)
        self.agency.refresh_from_db()
        # Notes version untouched, merits jumped from 0→1.
        self.assertEqual(self.agency.section_versions.get("notes"), 1)
        self.assertEqual(self.agency.section_versions.get("merits"), 1)

    # ------------------------------------------------------------------
    # Permissions — admin-only and notes membership.
    # ------------------------------------------------------------------

    def test_admin_only_sections_reject_non_admin(self):
        """``header``, ``alliance``, ``attributes``, ``merits``, ``flaws``,
        ``integrity`` etc. are admin-only — non-admins get 403."""
        self.client.login(username="player1", password="testpass123")
        admin_only_sections = [
            ("header", {"name": "X"}),
            ("alliance", {"alliance": {"countries": ["X"]}}),
            ("attributes", {"attributes": {"power": {"Industry": 1}}}),
            ("merits", {"merits": []}),
            ("flaws", {"flaws": []}),
            ("integrity", {"integrity": 5}),
            ("specializations", {"specializations": []}),
            ("assets", {"assets": []}),
            ("fleet", {"fleet": []}),
            ("history", {"history": []}),
            ("admin-flags", {"mapColor": "#abcdef"}),
        ]
        for key, body in admin_only_sections:
            url = f"/api/agencies/{self.agency.id}/section/{key}/"
            resp = self.client.patch(
                url, data=json.dumps(body), content_type="application/json",
            )
            self.assertEqual(
                resp.status_code, 403,
                msg=f"{key} should be admin-only — got {resp.status_code}",
            )

    def test_player_member_can_write_notes_on_own_agency(self):
        self.client.login(username="player1", password="testpass123")
        url = f"/api/agencies/{self.agency.id}/section/notes/"
        resp = self.client.patch(
            url,
            data=json.dumps({"notes": "player wrote this"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.agency.refresh_from_db()
        self.assertEqual(self.agency.notes, "player wrote this")

    def test_outsider_cannot_write_notes_on_other_player_agency(self):
        # outsider has no character / no workspace assignment.
        self.client.login(username="outsider1", password="testpass123")
        url = f"/api/agencies/{self.agency.id}/section/notes/"
        resp = self.client.patch(
            url,
            data=json.dumps({"notes": "trespass"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)


class AdminFlagsSectionTests(TestCase):
    """The bundled ``admin-flags`` endpoint — five fields share one slot."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = _make_user("flags_admin", is_superuser=True)
        cls.agency = Agency.objects.create(name="Flag Test", is_player_agency=False)

    def setUp(self):
        self.client = Client()
        self.client.login(username="flags_admin", password="testpass123")

    def test_each_admin_flag_writes_through_and_shares_one_version(self):
        url = f"/api/agencies/{self.agency.id}/section/admin-flags/"
        # Each PATCH targets a single flag, but they all bump the same
        # ``admin-flags`` version slot — they don't interfere.
        steps = [
            ({"mapColor": "#ff0000"}, "map_color", "#ff0000"),
            ({"isNuclearPower": True}, "is_nuclear_power", True),
            ({"sweepPool": 7}, "sweep_pool", 7),
            ({"zeroDayPool": 3}, "zero_day_pool", 3),
            ({"isHidden": False}, "is_hidden", False),  # leave hidden=False so we still see it
        ]
        for i, (payload, attr, expected) in enumerate(steps):
            resp = self.client.patch(
                url,
                data=json.dumps(payload),
                content_type="application/json",
                HTTP_IF_MATCH=str(i),
            )
            self.assertEqual(resp.status_code, 200, msg=f"step {i}: {payload}")
            self.assertEqual(resp["ETag"], str(i + 1))
            self.agency.refresh_from_db()
            self.assertEqual(getattr(self.agency, attr), expected)
            self.assertEqual(
                self.agency.section_versions.get("admin-flags"), i + 1,
            )

    def test_admin_flags_invalid_int_returns_400(self):
        url = f"/api/agencies/{self.agency.id}/section/admin-flags/"
        resp = self.client.patch(
            url,
            data=json.dumps({"sweepPool": "not-a-number"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)


class BaseSectionPatchTests(TestCase):
    """Behaviour of the per-base ``/bases/<id>/section/<key>/`` PATCH."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = _make_user("base_admin", is_superuser=True)
        cls.player = _make_user("base_player")
        cls.agency = Agency.objects.create(
            name="Player Agency", is_player_agency=True, experience=10000,
        )
        cls.base = Base.objects.create(
            agency=cls.agency,
            name="Alpha",
            location_type="safe_house",
            facilities=[{"key": "general", "level": 3}],
            merits=["secure"],
            equipment=["radio"],
        )
        _make_player_member_setup(cls.agency, cls.player)

    def setUp(self):
        self.client = Client()

    def _url(self, section_key):
        return (
            f"/api/agencies/{self.agency.id}/bases/{self.base.id}/"
            f"section/{section_key}/"
        )

    # ------------------------------------------------------------------
    # Round-trip coverage — every section_key must work for at least one
    # admin write and report the bumped version.
    # ------------------------------------------------------------------

    def test_each_base_section_round_trips(self):
        self.client.login(username="base_admin", password="testpass123")
        steps = [
            ("name", {"name": "Renamed"}, lambda b: b.name == "Renamed"),
            ("location", {"location": "black_site"},
                lambda b: b.location_type == "black_site"),
            ("merits", {"merits": ["secure", "extra_large"]},
                lambda b: b.merits == ["secure", "extra_large"]),
            ("facilities", {"facilities": [
                {"key": "general", "level": 3},
                {"key": "barracks", "level": 1},
            ]}, lambda b: len(b.facilities) == 2),
            ("workspaces", {"workspaces": [
                {"level": 1, "assignedType": "character",
                 "assignedTo": Character.objects.first().id},
                {"level": 2, "assignedType": None, "assignedTo": None},
            ]}, lambda b: len(b.workspaces) == 2),
            ("equipment", {"equipment": ["radio", "internal_security"]},
                lambda b: b.equipment == ["radio", "internal_security"]),
            ("departments", {"departments": [{"key": "military", "thrive": 5}]},
                lambda b: b.departments == [{"key": "military", "thrive": 5}]),
            ("notes", {"notes": "field report"},
                lambda b: b.notes == "field report"),
            ("geo", {"latitude": 12.34, "longitude": -56.78},
                lambda b: b.latitude == 12.34 and b.longitude == -56.78),
            ("hidden", {"hidden": True}, lambda b: b.is_hidden is True),
            ("classified", {"classified": ["facilities"]},
                lambda b: b.hidden_sections == ["facilities"]),
        ]
        expected_version = 0
        for key, body, check in steps:
            resp = self.client.patch(
                self._url(key),
                data=json.dumps(body),
                content_type="application/json",
                HTTP_IF_MATCH=str(expected_version),
            )
            self.assertEqual(
                resp.status_code, 200,
                msg=f"section {key}: HTTP {resp.status_code} body={resp.content!r}",
            )
            expected_version += 1
            self.assertEqual(resp["ETag"], str(expected_version))
            self.base.refresh_from_db()
            self.assertEqual(self.base.version, expected_version)
            self.assertTrue(check(self.base), msg=f"section {key} state check failed")
            # ``hidden=True`` would block subsequent visibility from non-admins;
            # since we're admin throughout, that's fine. Reset hidden after we
            # tested it so later steps still operate.
            if key == "hidden":
                self.base.is_hidden = False
                self.base.save(update_fields=["is_hidden"])

    # ------------------------------------------------------------------
    # Field name aliases — the contract accepts both spellings.
    # ------------------------------------------------------------------

    def test_location_section_accepts_locationType_alias(self):
        self.client.login(username="base_admin", password="testpass123")
        resp = self.client.patch(
            self._url("location"),
            data=json.dumps({"locationType": "estate"}),
            content_type="application/json",
            HTTP_IF_MATCH="0",
        )
        self.assertEqual(resp.status_code, 200)
        self.base.refresh_from_db()
        self.assertEqual(self.base.location_type, "estate")

    def test_hidden_section_accepts_isHidden_alias(self):
        self.client.login(username="base_admin", password="testpass123")
        resp = self.client.patch(
            self._url("hidden"),
            data=json.dumps({"isHidden": True}),
            content_type="application/json",
            HTTP_IF_MATCH="0",
        )
        self.assertEqual(resp.status_code, 200)
        self.base.refresh_from_db()
        self.assertTrue(self.base.is_hidden)

    def test_classified_section_accepts_hiddenSections_alias(self):
        self.client.login(username="base_admin", password="testpass123")
        resp = self.client.patch(
            self._url("classified"),
            data=json.dumps({"hiddenSections": ["equipment"]}),
            content_type="application/json",
            HTTP_IF_MATCH="0",
        )
        self.assertEqual(resp.status_code, 200)
        self.base.refresh_from_db()
        self.assertEqual(self.base.hidden_sections, ["equipment"])

    # ------------------------------------------------------------------
    # Unknown section_key.
    # ------------------------------------------------------------------

    def test_unknown_section_key_returns_404(self):
        self.client.login(username="base_admin", password="testpass123")
        resp = self.client.patch(
            f"/api/agencies/{self.agency.id}/bases/{self.base.id}/"
            f"section/nonsense/",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 404)

    # ------------------------------------------------------------------
    # Player permissions — additive only.
    # ------------------------------------------------------------------

    def test_player_can_add_base_merit(self):
        self.client.login(username="base_player", password="testpass123")
        resp = self.client.patch(
            self._url("merits"),
            data=json.dumps({"merits": ["secure", "extra_large"]}),
            content_type="application/json",
            HTTP_IF_MATCH="0",
        )
        self.assertEqual(resp.status_code, 200)
        self.base.refresh_from_db()
        self.assertEqual(set(self.base.merits), {"secure", "extra_large"})

    def test_player_cannot_remove_base_merit(self):
        """Old bug: silent drop. New contract: explicit 403."""
        self.client.login(username="base_player", password="testpass123")
        resp = self.client.patch(
            self._url("merits"),
            data=json.dumps({"merits": []}),  # tries to remove "secure"
            content_type="application/json",
            HTTP_IF_MATCH="0",
        )
        self.assertEqual(resp.status_code, 403)
        self.base.refresh_from_db()
        # Original merit is still there — no silent drop.
        self.assertIn("secure", self.base.merits)

    def test_player_can_add_facility_but_not_remove(self):
        self.client.login(username="base_player", password="testpass123")

        # Add — OK.
        resp = self.client.patch(
            self._url("facilities"),
            data=json.dumps({"facilities": [
                {"key": "general", "level": 3},
                {"key": "barracks", "level": 1},
            ]}),
            content_type="application/json",
            HTTP_IF_MATCH="0",
        )
        self.assertEqual(resp.status_code, 200)

        # Remove — 403.
        self.base.refresh_from_db()
        resp = self.client.patch(
            self._url("facilities"),
            data=json.dumps({"facilities": [
                {"key": "general", "level": 3},  # barracks dropped
            ]}),
            content_type="application/json",
            HTTP_IF_MATCH=str(self.base.version),
        )
        self.assertEqual(resp.status_code, 403)

    def test_player_can_add_equipment_but_not_remove(self):
        self.client.login(username="base_player", password="testpass123")

        resp = self.client.patch(
            self._url("equipment"),
            data=json.dumps({"equipment": ["radio", "internal_security"]}),
            content_type="application/json",
            HTTP_IF_MATCH="0",
        )
        self.assertEqual(resp.status_code, 200)

        self.base.refresh_from_db()
        resp = self.client.patch(
            self._url("equipment"),
            data=json.dumps({"equipment": []}),
            content_type="application/json",
            HTTP_IF_MATCH=str(self.base.version),
        )
        self.assertEqual(resp.status_code, 403)

    # ------------------------------------------------------------------
    # Sequential 409 — the deterministic equivalent of the live-server
    # concurrent race below. Two clients both believe they hold version 0;
    # the second one (after the first commits) must get 409 + the winner's
    # state in ``current_value``.
    # ------------------------------------------------------------------

    def test_sequential_stale_if_match_on_facilities_returns_409(self):
        self.client.login(username="base_admin", password="testpass123")
        url = self._url("facilities")

        # Player A's commit succeeds — base.version: 0 → 1.
        resp_a = self.client.patch(
            url,
            data=json.dumps({"facilities": [
                {"key": "general", "level": 3},
                {"key": "barracks", "level": 1},
            ]}),
            content_type="application/json",
            HTTP_IF_MATCH="0",
        )
        self.assertEqual(resp_a.status_code, 200)
        self.assertEqual(resp_a["ETag"], "1")

        # Player B is still on the stale version — collide.
        resp_b = self.client.patch(
            url,
            data=json.dumps({"facilities": [
                {"key": "general", "level": 3},
                {"key": "laboratory", "level": 1},
            ]}),
            content_type="application/json",
            HTTP_IF_MATCH="0",
        )
        self.assertEqual(resp_b.status_code, 409)
        body = resp_b.json()
        self.assertEqual(body["current_version"], 1)
        # ``current_value`` must reflect Player A's state (the canonical
        # post-conflict view), not Player B's rejected payload.
        self.assertEqual(body["current_value"], [
            {"key": "general", "level": 3},
            {"key": "barracks", "level": 1},
        ])
        self.base.refresh_from_db()
        self.assertEqual(self.base.facilities, [
            {"key": "general", "level": 3},
            {"key": "barracks", "level": 1},
        ])
        self.assertEqual(self.base.version, 1)


class InitialFetchShapeTests(TestCase):
    """``GET /api/agencies/<id>/`` exposes the version dict and per-base version."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = _make_user("fetch_admin", is_superuser=True)
        cls.agency = Agency.objects.create(name="Fetch", is_player_agency=False)
        cls.base = Base.objects.create(agency=cls.agency, name="HQ")

    def setUp(self):
        self.client = Client()
        self.client.login(username="fetch_admin", password="testpass123")

    def test_initial_get_exposes_section_versions_and_base_version(self):
        resp = self.client.get(f"/api/agencies/{self.agency.id}/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("sectionVersions", body)
        self.assertIsInstance(body["sectionVersions"], dict)
        # bases[0].version is an int (default 0).
        self.assertEqual(body["bases"][0]["version"], 0)

    def test_section_patch_reflects_in_subsequent_get(self):
        # PATCH a section, then re-fetch and check the bumped value lands
        # in sectionVersions under the right key.
        self.client.patch(
            f"/api/agencies/{self.agency.id}/section/notes/",
            data=json.dumps({"notes": "x"}),
            content_type="application/json",
            HTTP_IF_MATCH="0",
        )
        body = self.client.get(f"/api/agencies/{self.agency.id}/").json()
        self.assertEqual(body["sectionVersions"].get("notes"), 1)


class LegacyShimTests(TestCase):
    """The legacy monolithic ``PUT`` endpoints must still work as shims."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = _make_user("shim_admin", is_superuser=True)
        cls.agency = Agency.objects.create(name="Shim", is_player_agency=False)
        cls.base = Base.objects.create(
            agency=cls.agency, name="ShimBase",
            facilities=[{"key": "general", "level": 1}],
        )

    def setUp(self):
        self.client = Client()
        self.client.login(username="shim_admin", password="testpass123")

    def test_legacy_put_agency_with_multifield_body_succeeds(self):
        """``PUT /api/agencies/<id>/`` with notes + merits in one body."""
        resp = self.client.put(
            f"/api/agencies/{self.agency.id}/",
            data=json.dumps({
                "notes": "via legacy PUT",
                "merits": [{"name": "Legacy", "value": 1}],
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.agency.refresh_from_db()
        self.assertEqual(self.agency.notes, "via legacy PUT")
        self.assertEqual(self.agency.merits, [{"name": "Legacy", "value": 1}])

    def test_legacy_put_base_with_multifield_body_bumps_version_once(self):
        """A multi-field PUT should bump ``Base.version`` exactly once,
        not once per field changed (atomic save)."""
        original_version = self.base.version
        resp = self.client.put(
            f"/api/agencies/{self.agency.id}/bases/{self.base.id}/",
            data=json.dumps({
                "name": "ShimBase 2",
                "notes": "shim notes",
                "merits": ["secure"],
                "equipment": ["radio"],
            }),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.base.refresh_from_db()
        self.assertEqual(self.base.version, original_version + 1)
        self.assertEqual(self.base.name, "ShimBase 2")
        self.assertEqual(self.base.notes, "shim notes")
        self.assertEqual(self.base.merits, ["secure"])
        self.assertEqual(self.base.equipment, ["radio"])


# ---------------------------------------------------------------------------
# Concurrent-write regression — needs real HTTP, hence LiveServerTestCase.
# ---------------------------------------------------------------------------


class ConcurrentBaseFacilityWriteTests(LiveServerTestCase):
    """Regression test for the Bifrost bug.

    Two players add different facilities to the same base at the same time
    via the per-base ``facilities`` PATCH. Exactly one must win (200) and the
    other must lose (409) — never both win, never silent drop.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Make sure ``MCP_API_TOKEN`` is unset for these tests so the
        # default-CSRF-enforcement path is exercised.
        cls._old_token = os.environ.pop("MCP_API_TOKEN", None)

    @classmethod
    def tearDownClass(cls):
        if cls._old_token is not None:
            os.environ["MCP_API_TOKEN"] = cls._old_token
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.admin_a = _make_user("race_admin_a", is_superuser=True)
        self.admin_b = _make_user("race_admin_b", is_superuser=True)
        self.agency = Agency.objects.create(
            name="Bifrost Agency", is_player_agency=True, experience=100000,
        )
        self.base = Base.objects.create(
            agency=self.agency,
            name="Bifrost Hub",
            location_type="military_base",
            facilities=[{"key": "general", "level": 3}],
            version=0,
        )

    def _login(self, session, username, password="testpass123"):
        """Authenticate ``session`` against the live server.

        Steps:
          1. GET /accounts/login/ — receive the CSRF cookie.
          2. POST credentials with the X-CSRFToken header / cookie pair.
        """
        login_url = f"{self.live_server_url}/accounts/login/"
        resp = session.get(login_url)
        self.assertEqual(resp.status_code, 200)
        token = session.cookies.get("csrftoken")
        self.assertIsNotNone(token, "csrftoken cookie must be set on login GET")
        resp = session.post(
            login_url,
            data={
                "username": username,
                "password": password,
                "csrfmiddlewaretoken": token,
            },
            headers={"Referer": login_url},
            allow_redirects=False,
        )
        self.assertIn(resp.status_code, (200, 302),
                      msg=f"login failed: {resp.status_code} {resp.text[:200]}")

    def _patch(self, session, url, payload, if_match):
        """PATCH with CSRF token attached. Returns the requests.Response."""
        token = session.cookies.get("csrftoken")
        headers = {
            "Content-Type": "application/json",
            "X-CSRFToken": token,
            "If-Match": str(if_match),
            "Referer": self.live_server_url + "/",
        }
        return session.patch(url, data=json.dumps(payload), headers=headers)

    def test_concurrent_facility_adds_yield_one_409(self):
        """Two simultaneous additive PATCHes — one wins, one collides."""
        session_a = requests.Session()
        session_b = requests.Session()
        self._login(session_a, "race_admin_a")
        self._login(session_b, "race_admin_b")

        url = (
            f"{self.live_server_url}/api/agencies/{self.agency.id}/"
            f"bases/{self.base.id}/section/facilities/"
        )

        payload_a = {"facilities": [
            {"key": "general", "level": 3},
            {"key": "barracks", "level": 1},  # A's pick
        ]}
        payload_b = {"facilities": [
            {"key": "general", "level": 3},
            {"key": "laboratory", "level": 1},  # B's pick
        ]}

        # Use a barrier to ensure both threads release at the exact same
        # moment so the requests overlap on the wire / DB lock.
        barrier = threading.Barrier(2)

        def fire(session, payload):
            barrier.wait(timeout=5)
            return self._patch(session, url, payload, if_match=0)

        with ThreadPoolExecutor(max_workers=2) as pool:
            future_a = pool.submit(fire, session_a, payload_a)
            future_b = pool.submit(fire, session_b, payload_b)
            resp_a = future_a.result(timeout=10)
            resp_b = future_b.result(timeout=10)

        statuses = sorted([resp_a.status_code, resp_b.status_code])
        self.assertEqual(
            statuses, [200, 409],
            msg=(
                "Concurrent additive writes must resolve as one 200 + one "
                f"409 — got {statuses}. A={resp_a.text[:200]} "
                f"B={resp_b.text[:200]}"
            ),
        )

        winner = resp_a if resp_a.status_code == 200 else resp_b
        loser = resp_b if resp_a.status_code == 200 else resp_a
        winner_payload = payload_a if winner is resp_a else payload_b

        # Winner: ETag = 1, body version = 1.
        self.assertEqual(winner.headers.get("ETag"), "1")
        self.assertEqual(winner.json()["version"], 1)

        # Loser: 409, current_version = 1, current_value = winner's facilities.
        loser_body = loser.json()
        self.assertEqual(loser_body["current_version"], 1)
        self.assertEqual(loser_body["current_value"], winner_payload["facilities"])

        # DB matches the winner — the loser's pick was NOT silently merged.
        self.base.refresh_from_db()
        self.assertEqual(self.base.version, 1)


# ---------------------------------------------------------------------------
# Projects-array CAS regression tests (Phase 4 — extending the section
# concurrency contract to per-project endpoints).
#
# Every per-project endpoint (fringe-effect, stimulants, dark-grants,
# unlock, prodigy assign/unassign, complete, roll, ...) shares the
# ``projects`` section version slot via ``_with_projects_cas``. The
# trade-off is that two concurrent writers to *different* projects
# share one slot — force-writes silently retry up to 5 times so
# the user sees a 200; If-Match writes 409 immediately.
# ---------------------------------------------------------------------------


class ProjectsSectionPatchTests(TestCase):
    """The new ``/api/agencies/<id>/section/projects/`` PATCH endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = _make_user("proj_admin", is_superuser=True)
        cls.player = _make_user("proj_player")
        cls.agency = Agency.objects.create(
            name="Project Test Agency",
            is_player_agency=True,
            projects=[
                {"name": "Alpha", "completionScore": 0, "fringe": False},
                {"name": "Beta", "completionScore": 5, "fringe": True},
            ],
        )
        cls.base = Base.objects.create(
            agency=cls.agency, name="HQ", location_type="safe_house",
        )
        _make_player_member_setup(cls.agency, cls.player)

    def setUp(self):
        self.client = Client()

    def _url(self):
        return f"/api/agencies/{self.agency.id}/section/projects/"

    def test_section_projects_endpoint_round_trips(self):
        """200 path: PATCH replaces the projects list and bumps the version."""
        self.client.login(username="proj_admin", password="testpass123")
        new_projects = [
            {"name": "Alpha", "completionScore": 1, "fringe": False},
            {"name": "Beta", "completionScore": 5, "fringe": True},
            {"name": "Gamma", "completionScore": 0, "fringe": False},
        ]
        resp = self.client.patch(
            self._url(),
            data=json.dumps({"projects": new_projects}),
            content_type="application/json",
            HTTP_IF_MATCH="0",
        )
        self.assertEqual(resp.status_code, 200, msg=resp.content)
        body = resp.json()
        self.assertEqual(body["version"], 1)
        self.assertEqual(resp["ETag"], "1")
        self.assertEqual(len(body["projects"]), 3)
        self.assertEqual(body["projects"][0]["completionScore"], 1)

        self.agency.refresh_from_db()
        self.assertEqual(len(self.agency.projects), 3)
        self.assertEqual(self.agency.section_versions.get("projects"), 1)

    def test_section_projects_endpoint_409_on_stale_if_match(self):
        """409 path: stale If-Match returns canonical state."""
        self.client.login(username="proj_admin", password="testpass123")
        self.agency.section_versions = {"projects": 4}
        self.agency.save(update_fields=["section_versions"])

        resp = self.client.patch(
            self._url(),
            data=json.dumps({"projects": [{"name": "Stale"}]}),
            content_type="application/json",
            HTTP_IF_MATCH="1",
        )
        self.assertEqual(resp.status_code, 409)
        body = resp.json()
        self.assertEqual(body["current_version"], 4)
        self.assertEqual(len(body["current_value"]), 2)

    def test_section_projects_endpoint_admin_only(self):
        """Player members cannot replace the entire projects list."""
        self.client.login(username="proj_player", password="testpass123")
        resp = self.client.patch(
            self._url(),
            data=json.dumps({"projects": []}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_section_projects_endpoint_logs_completion_changes(self):
        """GM adjusting completionScore via section endpoint logs a
        ProjectRollLog entry — preserves the legacy audit trail."""
        from agencies.models import ProjectRollLog

        self.client.login(username="proj_admin", password="testpass123")
        before = ProjectRollLog.objects.filter(
            agency=self.agency, character_name="GM",
        ).count()

        new_projects = [
            {"name": "Alpha", "completionScore": 7, "fringe": False},  # 0 -> 7
            {"name": "Beta", "completionScore": 5, "fringe": True},
        ]
        resp = self.client.patch(
            self._url(),
            data=json.dumps({"projects": new_projects}),
            content_type="application/json",
            HTTP_IF_MATCH="0",
        )
        self.assertEqual(resp.status_code, 200)

        after = ProjectRollLog.objects.filter(
            agency=self.agency, character_name="GM",
        ).count()
        self.assertEqual(after, before + 1)

    def test_section_projects_endpoint_validates_list_type(self):
        """400 on non-list payload."""
        self.client.login(username="proj_admin", password="testpass123")
        resp = self.client.patch(
            self._url(),
            data=json.dumps({"projects": "not a list"}),
            content_type="application/json",
            HTTP_IF_MATCH="0",
        )
        self.assertEqual(resp.status_code, 400)

    def test_section_projects_strips_computed_pool(self):
        """``computedPool`` (server-computed at serialise time) must not
        round-trip into storage. Mirrors the legacy PUT shim behaviour."""
        self.client.login(username="proj_admin", password="testpass123")
        new_projects = [
            {
                "name": "Alpha",
                "completionScore": 0,
                "fringe": False,
                "computedPool": {"pool": 5, "parts": []},  # should be stripped
            },
        ]
        resp = self.client.patch(
            self._url(),
            data=json.dumps({"projects": new_projects}),
            content_type="application/json",
            HTTP_IF_MATCH="0",
        )
        self.assertEqual(resp.status_code, 200)
        self.agency.refresh_from_db()
        self.assertNotIn("computedPool", self.agency.projects[0])


class PerProjectEndpointVersionBumpTests(TestCase):
    """Per-project endpoints (dark-grants, fringe-effect, complete, ...)
    must bump the shared ``projects`` section version slot. This guards
    the contract that a section-level reader fetching the projects
    version sees an up-to-date value after any per-project mutation."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = _make_user("perproj_admin", is_superuser=True)
        cls.agency = Agency.objects.create(
            name="PerProj Agency",
            is_player_agency=True,
            experience=100,
            integrity=10,
            attributes={
                "power": {"Industry": 1},
                "finesse": {},
                "resistance": {},
            },
            projects=[
                {
                    "name": "Alpha", "completionScore": 0, "fringe": False,
                    "completionEffects": {
                        "attributeChanges": [
                            {"category": "power", "name": "Industry", "value": 1},
                        ],
                        "integrityChange": 0,
                    },
                },
            ],
        )

    def setUp(self):
        self.client = Client()
        self.client.login(username="perproj_admin", password="testpass123")

    def test_complete_project_bumps_projects_version(self):
        """Per-project endpoint (completion) bumps the shared slot so
        later section-level writers see a non-zero starting version."""
        self.assertEqual(
            (self.agency.section_versions or {}).get("projects", 0), 0,
        )
        resp = self.client.post(
            f"/api/agencies/{self.agency.id}/projects/0/complete/",
        )
        self.assertEqual(resp.status_code, 200, msg=resp.content)

        self.agency.refresh_from_db()
        self.assertEqual(self.agency.section_versions.get("projects"), 1)
        self.assertTrue(self.agency.projects[0]["completed"])
        # Attribute change applied through the CAS extra_update_fields.
        self.assertEqual(self.agency.attributes["power"]["Industry"], 2)


class ConcurrentProjectWriteTests(LiveServerTestCase):
    """Live-server regression for the per-project concurrency fix.

    Two scenarios:
      1. Two admins both PATCH /section/projects/ (full-list replace) —
         must resolve as exactly one 200 + one 409.
      2. Two admins both POST to per-project endpoints with If-Match — the
         CAS must produce one 200 + one 409 (no silent drop).

    The force-write path (no If-Match) for per-project endpoints is
    expected to retry internally and almost always produce two 200s in
    the two-different-projects case; we don't pin that exact behaviour
    here because it depends on retry timing, but we verify the DB ends
    up consistent (no lost update).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._old_token = os.environ.pop("MCP_API_TOKEN", None)

    @classmethod
    def tearDownClass(cls):
        if cls._old_token is not None:
            os.environ["MCP_API_TOKEN"] = cls._old_token
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        self.admin_a = _make_user("proj_race_a", is_superuser=True)
        self.admin_b = _make_user("proj_race_b", is_superuser=True)
        self.agency = Agency.objects.create(
            name="Project Race Agency",
            is_player_agency=True,
            experience=100000,
            integrity=10,
            projects=[
                {"name": "Alpha", "completionScore": 0, "fringe": True},
                {"name": "Beta",  "completionScore": 0, "fringe": True},
            ],
        )
        self.base = Base.objects.create(
            agency=self.agency, name="Race Hub",
            location_type="military_base",
            facilities=[{"key": "general", "level": 3}],
            version=0,
        )

    def _login(self, session, username, password="testpass123"):
        login_url = f"{self.live_server_url}/accounts/login/"
        resp = session.get(login_url)
        self.assertEqual(resp.status_code, 200)
        token = session.cookies.get("csrftoken")
        self.assertIsNotNone(token, "csrftoken cookie must be set on login GET")
        resp = session.post(
            login_url,
            data={
                "username": username, "password": password,
                "csrfmiddlewaretoken": token,
            },
            headers={"Referer": login_url},
            allow_redirects=False,
        )
        self.assertIn(resp.status_code, (200, 302),
                      msg=f"login failed: {resp.status_code} {resp.text[:200]}")

    def _patch(self, session, url, payload, *, if_match=None):
        token = session.cookies.get("csrftoken")
        headers = {
            "Content-Type": "application/json",
            "X-CSRFToken": token,
            "Referer": self.live_server_url + "/",
        }
        if if_match is not None:
            headers["If-Match"] = str(if_match)
        return session.patch(url, data=json.dumps(payload), headers=headers)

    def _post(self, session, url, payload, *, if_match=None):
        token = session.cookies.get("csrftoken")
        headers = {
            "Content-Type": "application/json",
            "X-CSRFToken": token,
            "Referer": self.live_server_url + "/",
        }
        if if_match is not None:
            headers["If-Match"] = str(if_match)
        return session.post(url, data=json.dumps(payload), headers=headers)

    def test_concurrent_full_list_project_replaces_yield_one_409(self):
        """Two admins both PATCH /section/projects/ with different
        project lists; exactly one 200, one 409 — the legacy silent-drop
        is gone."""
        session_a = requests.Session()
        session_b = requests.Session()
        self._login(session_a, "proj_race_a")
        self._login(session_b, "proj_race_b")

        url = (
            f"{self.live_server_url}/api/agencies/{self.agency.id}/"
            f"section/projects/"
        )

        payload_a = {"projects": [
            {"name": "Alpha", "completionScore": 1, "fringe": True},
            {"name": "Beta",  "completionScore": 0, "fringe": True},
        ]}
        payload_b = {"projects": [
            {"name": "Alpha", "completionScore": 0, "fringe": True},
            {"name": "Beta",  "completionScore": 7, "fringe": True},  # B's edit
        ]}

        barrier = threading.Barrier(2)

        def fire(session, payload):
            barrier.wait(timeout=5)
            return self._patch(session, url, payload, if_match=0)

        with ThreadPoolExecutor(max_workers=2) as pool:
            future_a = pool.submit(fire, session_a, payload_a)
            future_b = pool.submit(fire, session_b, payload_b)
            resp_a = future_a.result(timeout=10)
            resp_b = future_b.result(timeout=10)

        statuses = sorted([resp_a.status_code, resp_b.status_code])
        self.assertEqual(
            statuses, [200, 409],
            msg=(
                "Concurrent project-list writes must resolve as one 200 + one "
                f"409 — got {statuses}. A={resp_a.text[:200]} B={resp_b.text[:200]}"
            ),
        )

        winner = resp_a if resp_a.status_code == 200 else resp_b
        loser = resp_b if resp_a.status_code == 200 else resp_a

        self.assertEqual(winner.headers.get("ETag"), "1")
        self.assertEqual(winner.json()["version"], 1)

        loser_body = loser.json()
        self.assertEqual(loser_body["current_version"], 1)
        # current_value reflects the canonical (winner's) state — the
        # client uses this to rebase.
        self.assertEqual(len(loser_body["current_value"]), 2)

    def test_concurrent_per_project_if_match_collide(self):
        """Two admins both PATCH /section/projects/ with overlapping
        edits and matching If-Match=0 — exactly one 200 + one 409.

        This is the same race the per-project endpoints must defend
        against: if both clients believe they hold version 0 and try to
        edit different fields of different projects, the slower writer
        must see 409 (not silently lose its work). We use the section
        endpoint here because it's the cleanest If-Match-pinned write
        path; the per-project endpoints share the same CAS slot, so
        defending it here proves the contract for all of them.
        """
        session_a = requests.Session()
        session_b = requests.Session()
        self._login(session_a, "proj_race_a")
        self._login(session_b, "proj_race_b")

        url = (
            f"{self.live_server_url}/api/agencies/{self.agency.id}/"
            f"section/projects/"
        )

        payload_a = {"projects": [
            {"name": "Alpha", "completionScore": 99, "fringe": True},  # A edits Alpha
            {"name": "Beta",  "completionScore": 0, "fringe": True},
        ]}
        payload_b = {"projects": [
            {"name": "Alpha", "completionScore": 0, "fringe": True},
            {"name": "Beta",  "completionScore": 99, "fringe": True},  # B edits Beta
        ]}

        barrier = threading.Barrier(2)

        def fire(session, payload):
            barrier.wait(timeout=5)
            return self._patch(session, url, payload, if_match=0)

        with ThreadPoolExecutor(max_workers=2) as pool:
            future_a = pool.submit(fire, session_a, payload_a)
            future_b = pool.submit(fire, session_b, payload_b)
            resp_a = future_a.result(timeout=10)
            resp_b = future_b.result(timeout=10)

        statuses = sorted([resp_a.status_code, resp_b.status_code])
        self.assertEqual(
            statuses, [200, 409],
            msg=f"got {statuses}. A={resp_a.text[:200]} B={resp_b.text[:200]}",
        )

        # The DB matches exactly the winner — no merge of A's and B's edits.
        self.agency.refresh_from_db()
        self.assertEqual(self.agency.section_versions.get("projects"), 1)
        winner_payload = (
            payload_a if resp_a.status_code == 200 else payload_b
        )
        for i, proj in enumerate(winner_payload["projects"]):
            self.assertEqual(
                self.agency.projects[i]["completionScore"],
                proj["completionScore"],
            )

    def test_concurrent_per_project_force_writes_both_succeed(self):
        """Force-writes (no If-Match) on per-project endpoints retry on
        CAS miss, so concurrent edits to *different* projects should
        both eventually succeed without lost updates. This is the
        legacy compat path: existing UI sites don't send If-Match yet,
        so the server must absorb the race for them."""
        session_a = requests.Session()
        session_b = requests.Session()
        self._login(session_a, "proj_race_a")
        self._login(session_b, "proj_race_b")

        # Both admins assign a fringe-effect (gene_manipulation +
        # sleep_deprivation) — different fields, different projects.
        url_a = (
            f"{self.live_server_url}/api/agencies/{self.agency.id}/"
            f"projects/0/fringe-effect/"
        )
        url_b = (
            f"{self.live_server_url}/api/agencies/{self.agency.id}/"
            f"projects/1/fringe-effect/"
        )

        barrier = threading.Barrier(2)

        def fire_a():
            barrier.wait(timeout=5)
            return self._post(session_a, url_a, {"effect": "gene_manipulation"})

        def fire_b():
            barrier.wait(timeout=5)
            return self._post(session_b, url_b, {"effect": "sleep_deprivation"})

        with ThreadPoolExecutor(max_workers=2) as pool:
            future_a = pool.submit(fire_a)
            future_b = pool.submit(fire_b)
            resp_a = future_a.result(timeout=15)
            resp_b = future_b.result(timeout=15)

        # Both must succeed (the helper retries on CAS miss for force
        # writes). If either is 409, the retry budget was exhausted —
        # rare under normal load but possible if both writers keep
        # racing in lockstep. Treat as a flake to investigate, not a
        # hard failure.
        statuses = sorted([resp_a.status_code, resp_b.status_code])
        self.assertEqual(
            statuses, [200, 200],
            msg=(
                "Force-write per-project writes to different projects must both "
                f"succeed via CAS retry — got {statuses}. "
                f"A={resp_a.text[:200]} B={resp_b.text[:200]}"
            ),
        )

        # Both edits landed: project 0 has gene_manipulation, project 1
        # has sleep_deprivation. Neither edit was silently dropped.
        self.agency.refresh_from_db()
        self.assertTrue(self.agency.projects[0].get("geneManipulation"))
        self.assertTrue(self.agency.projects[1].get("sleepDeprivation"))
        # Version slot bumped twice — once per edit.
        self.assertEqual(self.agency.section_versions.get("projects"), 2)
