"""Tests for the star-intel scanning system (Phase 1 — engine).

Covers the new dice/uncertainty math, observatory listing, and the
observatory-scan endpoint incl. the GM scanning-turn gate, discovery gate,
and the one-scan-per-observatory-per-turn rule.
"""

import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from agencies.models import Agency, Base
from characters.models import Character
from exodus.models import SiteSettings
from starmap.models import AgencyScan, PublicScanRecord, StarSystem
from starmap.serializers import (
    base_scan_target, effective_scan_target, list_agency_observatories,
    observatory_dice, scan_uncertainty,
)


class ScanMathTests(TestCase):
    def test_observatory_dice(self):
        self.assertEqual(observatory_dice(0), 5)    # base observatory
        self.assertEqual(observatory_dice(1), 10)   # + Ground Telescope
        self.assertEqual(observatory_dice(2), 15)   # + Deep-Space Tracking
        self.assertEqual(observatory_dice(3), 15)   # no higher upgrade

    def test_base_target_clamped(self):
        class S:
            difficulty_mod = 0
        s = S()
        self.assertEqual(base_scan_target(s), 15)
        s.difficulty_mod = 10
        self.assertEqual(base_scan_target(s), 25)
        s.difficulty_mod = -10
        self.assertEqual(base_scan_target(s), 5)
        s.difficulty_mod = 99
        self.assertEqual(base_scan_target(s), 25)  # clamp upper

    def test_uncertainty(self):
        self.assertEqual(scan_uncertainty(15, 15), 0)    # perfect
        self.assertEqual(scan_uncertainty(12, 15), 75)   # 3 short * 25
        self.assertEqual(scan_uncertainty(0, 15), 375)   # uncapped (15 short * 25)
        self.assertEqual(scan_uncertainty(20, 15), 0)    # over target = perfect

    def test_effective_target_false_penalty(self):
        class S:
            difficulty_mod = 0
        s = S()
        self.assertEqual(effective_scan_target(s, 0), 15)
        self.assertEqual(effective_scan_target(s, 2), 21)   # +3 each
        self.assertEqual(effective_scan_target(s, 99), 30)  # +15 cap


class ObservatoryScanTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.gm = User.objects.create_superuser("gm3", "gm3@example.com", "pw")
        self.client = Client()
        self.client.force_login(self.gm)
        self.agency = Agency.objects.create(name="Scan Agency", is_player_agency=True)
        self.base = Base.objects.create(
            agency=self.agency, name="Obs Base",
            facilities=[{"key": "observatory", "level": 2}],
        )
        self.star = StarSystem.objects.create(
            name="Tau Ceti", x=1, y=2, z=3, distance=11.9, spectral_type="G8.5V",
            discovered=True, difficulty_mod=0, has_livable_planet=True,
            resources={"helium3": 40},
        )
        self.agency.scan_grant = 5
        self.agency.save()

    def _scan(self, base_id=None, star_id=None):
        return self.client.post(
            f"/api/agencies/{self.agency.id}/observatory-scan/",
            data=json.dumps({
                "baseId": base_id or self.base.id,
                "starSystemId": star_id or self.star.id,
            }),
            content_type="application/json",
        )

    def test_observatory_listing(self):
        obs = list_agency_observatories(self.agency)
        self.assertEqual(len(obs), 1)
        self.assertEqual(obs[0]["dice"], 15)  # level 2 = 15 dice
        self.assertEqual(obs[0]["baseId"], self.base.id)

    def test_scan_accumulates_and_sets_target(self):
        r = self._scan()
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["pool"], 15)
        self.assertEqual(d["target"], 15)
        self.assertEqual(d["accumulated"], d["successes"])
        self.assertEqual(d["uncertainty"], max(0, (15 - d["successes"]) * 25))
        scan = AgencyScan.objects.get(agency=self.agency, star_system=self.star)
        self.assertEqual(scan.current_successes, d["successes"])
        self.assertEqual(scan.required_successes, 15)

    def test_accumulation_is_monotonic(self):
        a = self._scan().json()["accumulated"]
        b = self._scan().json()["accumulated"]
        self.assertGreaterEqual(b, a)             # never reset

    def test_usage_recorded(self):
        self._scan()
        self.agency.refresh_from_db()
        self.assertEqual(self.agency.scan_usage[str(self.base.id)], 1)

    def test_unknown_observatory_rejected(self):
        r = self._scan(base_id=999999)
        self.assertEqual(r.status_code, 400)


class ScanGateTests(TestCase):
    """Gate enforcement with a real non-superuser player (agency resolved via
    character-workspace assignment)."""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user("player", "p@example.com", "pw")
        self.char = Character.objects.create(owner=self.user, name="Sci Officer")
        self.agency = Agency.objects.create(name="Player Agency", is_player_agency=True)
        self.base = Base.objects.create(
            agency=self.agency, name="Obs",
            facilities=[{"key": "observatory", "level": 1}],
            workspaces=[{"assignedType": "character", "assignedTo": self.char.id}],
        )
        self.star = StarSystem.objects.create(
            name="Sys", x=1, y=1, z=1, distance=5, spectral_type="M",
            discovered=True, difficulty_mod=0, resources={},
        )
        self.client = Client()
        self.client.force_login(self.user)
        self.agency.scan_grant = 2  # GM grant: 2 scans per observatory
        self.agency.save()

    def _scan(self, base_id=None, star_id=None):
        return self.client.post(
            f"/api/agencies/{self.agency.id}/observatory-scan/",
            data=json.dumps({
                "baseId": base_id or self.base.id,
                "starSystemId": star_id or self.star.id,
            }),
            content_type="application/json",
        )

    def test_player_can_scan_with_grant(self):
        r = self._scan()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["pool"], 10)  # level 1 = 10 dice

    def test_no_grant_blocks(self):
        self.agency.scan_grant = 0
        self.agency.save()
        r = self._scan()
        self.assertEqual(r.status_code, 400)
        self.assertIn("no scans remaining", r.json()["error"].lower())

    def test_first_scan_discovers_system(self):
        self.star.discovered = False
        self.star.save()
        r = self._scan()
        self.assertEqual(r.status_code, 200)        # scannable even if undiscovered
        self.star.refresh_from_db()
        self.assertTrue(self.star.discovered)       # first scan discovered it

    def test_observatory_exhausts_grant(self):
        # grant of 2 -> two scans OK, third blocked
        self.assertEqual(self._scan().status_code, 200)
        self.assertEqual(self._scan().status_code, 200)
        r3 = self._scan()
        self.assertEqual(r3.status_code, 400)
        self.assertIn("no scans remaining", r3.json()["error"].lower())

    def test_regrant_resets_usage(self):
        self._scan(); self._scan()                  # exhaust the grant of 2
        self.assertEqual(self._scan().status_code, 400)
        self.agency.scan_grant = 1                   # GM re-grants (resets usage)
        self.agency.scan_usage = {}
        self.agency.save()
        self.assertEqual(self._scan().status_code, 200)  # observatory free again

    def test_other_agency_forbidden(self):
        other = Agency.objects.create(name="Other", is_player_agency=True)
        r = self.client.post(
            f"/api/agencies/{other.id}/observatory-scan/",
            data=json.dumps({"baseId": self.base.id, "starSystemId": self.star.id}),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 403)


class PublicRecordTests(TestCase):
    """Phase 2 — publish/keep-private to the shared board + GM oversight."""

    def setUp(self):
        User = get_user_model()
        self.gm = User.objects.create_superuser("gm4", "gm4@example.com", "pw")
        self.client = Client()
        self.client.force_login(self.gm)
        self.agency = Agency.objects.create(name="Pub Agency", is_player_agency=True)
        self.star = StarSystem.objects.create(
            name="Wolf 359", x=1, y=1, z=1, distance=7.8, spectral_type="M6",
            discovered=True, difficulty_mod=0, has_livable_planet=True,
            resources={"helium3": 40},
        )
        # Pre-existing accumulated scan so there's data to publish.
        self.scan = AgencyScan.objects.create(
            agency=self.agency, star_system=self.star,
            current_successes=12, required_successes=15,
            scanned_resources={"helium3": {"min": 30, "max": 50, "unit": "loads"}},
        )

    def _publish(self, **body):
        b = {"starSystemId": self.star.id}
        b.update(body)
        return self.client.post(
            f"/api/agencies/{self.agency.id}/publish-scan/",
            data=json.dumps(b), content_type="application/json")

    def test_publish_creates_record(self):
        r = self._publish()
        self.assertEqual(r.status_code, 200)
        rec = PublicScanRecord.objects.get(agency=self.agency, star_system=self.star)
        self.assertFalse(rec.is_false)
        self.assertEqual(rec.uncertainty, 75)  # (15-12)*25
        self.assertIn("resources", rec.payload)

    def test_publish_requires_scan_data(self):
        other = StarSystem.objects.create(
            name="Empty", x=2, y=2, z=2, distance=3, spectral_type="K", discovered=True)
        r = self._publish(starSystemId=other.id)
        self.assertEqual(r.status_code, 400)

    def test_unpublish_deletes(self):
        self._publish()
        r = self.client.post(
            f"/api/agencies/{self.agency.id}/unpublish-scan/",
            data=json.dumps({"starSystemId": self.star.id}),
            content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(PublicScanRecord.objects.filter(
            agency=self.agency, star_system=self.star).exists())

    def test_publish_false_data(self):
        r = self._publish(isFalse=True, payload={"resources": {}, "livable": True}, uncertainty=5)
        self.assertEqual(r.status_code, 200)
        rec = PublicScanRecord.objects.get(agency=self.agency, star_system=self.star)
        self.assertTrue(rec.is_false)
        self.assertEqual(rec.uncertainty, 5)  # faked low to look authoritative

    def test_republish_updates_not_duplicates(self):
        self._publish()
        self._publish()
        self.assertEqual(PublicScanRecord.objects.filter(
            agency=self.agency, star_system=self.star).count(), 1)

    def test_gm_oversight_page_renders(self):
        self._publish(isFalse=True, payload={}, uncertainty=5)
        r = self.client.get("/gm/star-intel/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Wolf 359")
        self.assertContains(r, "FALSE")  # disinformation exposed to GM


class FalseDataDifficultyTests(TestCase):
    """Phase 3 — a false public record raises the effective scan target."""

    def setUp(self):
        User = get_user_model()
        self.gm = User.objects.create_superuser("gm5", "gm5@example.com", "pw")
        self.client = Client()
        self.client.force_login(self.gm)
        self.agency = Agency.objects.create(name="Scanner", is_player_agency=True)
        self.base = Base.objects.create(
            agency=self.agency, name="Obs",
            facilities=[{"key": "observatory", "level": 2}])
        self.other = Agency.objects.create(name="Liar", is_player_agency=True)
        self.star = StarSystem.objects.create(
            name="Disinfo Sys", x=1, y=1, z=1, distance=4, spectral_type="K",
            discovered=True, difficulty_mod=0, resources={})
        s = SiteSettings.load()
        s.scanning_turn_open = True
        s.scanning_turn_number = 1
        s.save()

    def test_false_record_raises_target(self):
        # Baseline target is 15.
        r0 = self.client.post(
            f"/api/agencies/{self.agency.id}/observatory-scan/",
            data=json.dumps({"baseId": self.base.id, "starSystemId": self.star.id}),
            content_type="application/json")
        self.assertEqual(r0.json()["target"], 15)
        # A rival plants two false records -> target rises by 2*3.
        PublicScanRecord.objects.create(agency=self.other, star_system=self.star, is_false=True, uncertainty=0, payload={})
        PublicScanRecord.objects.create(agency=self.agency, star_system=self.star, is_false=True, uncertainty=0, payload={})
        r1 = self.client.post(
            f"/api/agencies/{self.agency.id}/observatory-scan/",
            data=json.dumps({"baseId": self.base.id, "starSystemId": self.star.id}),
            content_type="application/json")
        self.assertEqual(r1.json()["target"], 21)  # 15 + 2*3
