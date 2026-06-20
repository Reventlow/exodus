"""Tests for the FTL jump + resupply mechanic (Phase 1).

Driven by a superuser so the user->agency character-workspace resolution
isn't needed; this exercises the full cost / fail-closed / logging / eligibility
logic of api_ship_jump and api_ship_resupply.
"""

import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from agencies.models import Agency
from exodus.models import SiteSettings
from starmap.models import StarSystem
from starships.models import (
    ClassModule,
    JumpLog,
    ShipModule,
    ShipModuleSection,
    ShipType,
    Starship,
    StarshipClass,
)


class JumpMechanicTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.gm = User.objects.create_superuser("gm", "gm@example.com", "pw")
        self.client = Client()
        self.client.force_login(self.gm)

        self.agency = Agency.objects.create(name="Test Agency")

        # base_maintenance 10 + a 0-delta FTL module => class maintenance == 10
        self.stype = ShipType.objects.create(
            key="jt_cruiser", name="Cruiser", base_maintenance=10, min_size=1, max_size=10,
        )
        self.section = ShipModuleSection.objects.create(key="jt_drive", name="Drive", order=1)
        self.ftl_mod = ShipModule.objects.create(
            key="jt_ftl", name="FTL Drive", section=self.section,
            provides_ftl=True, maintenance_delta=0,
        )
        self.ftl_class = StarshipClass.objects.create(
            name="FTL Cruiser", ship_type=self.stype, size=5, created_by=self.agency,
        )
        ClassModule.objects.create(starship_class=self.ftl_class, module=self.ftl_mod, quantity=1)

        # A class with no FTL drive.
        self.sublight_class = StarshipClass.objects.create(
            name="Sublight Cruiser", ship_type=self.stype, size=5, created_by=self.agency,
        )

        self.sol = StarSystem.objects.create(
            name="Sol", x=0, y=0, z=0, distance=0, spectral_type="G2V",
            is_sol=True, claimed_by=self.agency,
        )
        self.tau = StarSystem.objects.create(
            name="Tau Ceti", x=-7.17, y=-3.13, z=-8.06, distance=11.89, spectral_type="G8.5V",
        )
        self.near = StarSystem.objects.create(
            name="Proxima", x=1.0, y=0.0, z=0.0, distance=1.0, spectral_type="M5.5V",
        )
        self.omega = StarSystem.objects.create(
            name="Signal Omega", x=50, y=50, z=50, distance=86.6, spectral_type="?",
            is_endgame=True,
        )

        self.ship = Starship.objects.create(
            name="Endeavour", starship_class=self.ftl_class, agency=self.agency,
            status="active", maintenance_state=100, location=self.sol,
        )

        s = SiteSettings.load()
        s.show_ftl_jumps = True
        s.jump_economy_config = {}  # use defaults (maint_wear_per_jump 1.0, resupply 100)
        s.save()

    def _jump(self, target_id):
        return self.client.post(
            f"/api/starships/ships/{self.ship.id}/jump/",
            data=json.dumps({"target_system_id": target_id}),
            content_type="application/json",
        )

    def _resupply(self):
        return self.client.post(f"/api/starships/ships/{self.ship.id}/resupply/")

    # --- success path ---

    def test_jump_moves_ship_and_debits_condition(self):
        r = self._jump(self.tau.id)
        self.assertEqual(r.status_code, 200)
        self.ship.refresh_from_db()
        self.assertEqual(self.ship.location_id, self.tau.id)
        self.assertEqual(self.ship.maintenance_state, 90)  # 100 - max(1, round(10*1.0))
        log = JumpLog.objects.get(kind="jump")
        self.assertEqual(log.wear, 10)
        self.assertEqual(log.maintenance_basis, 10)
        self.assertGreater(log.distance_ly, 11.0)  # ~11.2 ly Sol->Tau Ceti
        self.assertEqual(log.from_system_name, "Sol")
        self.assertEqual(log.to_system_name, "Tau Ceti")

    def test_cost_is_flat_regardless_of_distance(self):
        # Near jump
        r1 = self._jump(self.near.id)
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r1.json()["wear"], 10)
        # Far jump from the new location
        r2 = self._jump(self.tau.id)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["wear"], 10)  # same flat cost despite far greater distance

    # --- eligibility / fail-closed ---

    def test_no_ftl_drive_rejected_no_op(self):
        self.ship.starship_class = self.sublight_class
        self.ship.save()
        r = self._jump(self.tau.id)
        self.assertEqual(r.status_code, 400)
        self.assertIn("No FTL drive", r.json()["error"])
        self.ship.refresh_from_db()
        self.assertEqual(self.ship.location_id, self.sol.id)  # did not move
        self.assertEqual(self.ship.maintenance_state, 100)    # not charged
        self.assertEqual(JumpLog.objects.count(), 0)

    def test_insufficient_condition_rejected_no_op(self):
        self.ship.maintenance_state = 5  # < wear of 10
        self.ship.save()
        r = self._jump(self.tau.id)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["required"], 10)
        self.assertEqual(r.json()["available"], 5)
        self.ship.refresh_from_db()
        self.assertEqual(self.ship.location_id, self.sol.id)
        self.assertEqual(self.ship.maintenance_state, 5)
        self.assertEqual(JumpLog.objects.count(), 0)

    def test_endgame_target_rejected(self):
        r = self._jump(self.omega.id)
        self.assertEqual(r.status_code, 400)
        self.assertIn("displacement range", r.json()["error"].lower())

    def test_jump_to_same_system_rejected(self):
        r = self._jump(self.sol.id)
        self.assertEqual(r.status_code, 400)

    def test_inactive_ship_cannot_jump(self):
        self.ship.status = "under_construction"
        self.ship.save()
        r = self._jump(self.tau.id)
        self.assertEqual(r.status_code, 400)

    def test_max_jump_ly_cap_enforced(self):
        s = SiteSettings.load()
        s.jump_economy_config = {"max_jump_ly": 5}  # Tau Ceti is ~11 ly
        s.save()
        r = self._jump(self.tau.id)
        self.assertEqual(r.status_code, 400)
        self.assertIn("drive range", r.json()["error"].lower())
        # but the near system (~1 ly) is fine
        self.assertEqual(self._jump(self.near.id).status_code, 200)

    # --- resupply ---

    def test_resupply_restores_at_claimed_system(self):
        self.ship.maintenance_state = 40
        self.ship.save()
        r = self._resupply()
        self.assertEqual(r.status_code, 200)
        self.ship.refresh_from_db()
        self.assertEqual(self.ship.maintenance_state, 100)
        log = JumpLog.objects.get(kind="resupply")
        self.assertEqual(log.wear, -60)  # negative = restored

    def test_resupply_rejected_at_unclaimed_system(self):
        self.ship.location = self.tau  # not claimed by the agency
        self.ship.maintenance_state = 40
        self.ship.save()
        r = self._resupply()
        self.assertEqual(r.status_code, 400)
        self.ship.refresh_from_db()
        self.assertEqual(self.ship.maintenance_state, 40)

    # --- gating ---

    def test_superuser_bypasses_disabled_gate(self):
        s = SiteSettings.load()
        s.show_ftl_jumps = False
        s.save()
        r = self._jump(self.tau.id)
        self.assertEqual(r.status_code, 200)  # GM bypass even when off for players


class JumpEconomyConfigTests(TestCase):
    def test_defaults_merge_over_partial_config(self):
        s = SiteSettings.load()
        s.jump_economy_config = {"maint_wear_per_jump": 2.5}
        s.save()
        cfg = SiteSettings.load().get_jump_economy()
        self.assertEqual(cfg["maint_wear_per_jump"], 2.5)   # override preserved
        self.assertEqual(cfg["resupply_amount"], 100)        # default filled in
        self.assertIn("fuel_keys", cfg)                      # phase-2 keys present
