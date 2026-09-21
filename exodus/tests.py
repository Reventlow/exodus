"""Tests for the site-settings view.

Focus: the settings page hosts several independent <form>s that all POST to the
same view. v0.15.60 hardened the handler so saving one section's form can no
longer silently reset settings that belong to a different section (the core
visibility flags, the charter, and the ship-slot toggle used to be written
unconditionally and were wiped by every other form's save).
"""

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse

from exodus.models import SiteSettings


class SettingsFormIsolationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("gm", "gm@example.com", "pw")
        self.client = Client()
        self.client.force_login(self.admin)
        self.url = reverse("site-settings")

        s = SiteSettings.load()
        s.show_world_map = True
        s.show_star_map = True
        s.show_public_star_map = True
        s.show_starships = True
        s.show_council = True
        s.lock_comms = False
        s.charter_text = "THE CHARTER"
        s.enforce_ship_slot_budget = True
        s.save()

    def _assert_core_intact(self, marker):
        s = SiteSettings.load()
        self.assertTrue(s.show_star_map, f"{marker} clobbered show_star_map")
        self.assertTrue(s.show_world_map, f"{marker} clobbered show_world_map")
        self.assertTrue(s.show_public_star_map, f"{marker} clobbered show_public_star_map")
        self.assertTrue(s.show_starships, f"{marker} clobbered show_starships")
        self.assertTrue(s.show_council, f"{marker} clobbered show_council")
        self.assertFalse(s.lock_comms, f"{marker} clobbered lock_comms")
        self.assertEqual(s.charter_text, "THE CHARTER", f"{marker} clobbered charter")
        self.assertTrue(s.enforce_ship_slot_budget, f"{marker} clobbered ship budget")

    def test_separate_forms_do_not_clobber_core_settings(self):
        # Each of these is its own <form> on the page; its POST carries only its
        # own marker and fields — never the core checkboxes.
        for marker in (
            "armor_submitted",
            "cover_submitted",
            "combat_npcs_submitted",
            "tweaks_submitted",
        ):
            resp = self.client.post(self.url, {marker: "1"})
            # PRG: the view redirects after a successful save.
            self.assertIn(resp.status_code, (200, 302))
            self._assert_core_intact(marker)

    def test_core_form_still_saves_visibility(self):
        # The main form carries the core marker; an absent checkbox => off.
        self.client.post(
            self.url,
            {"core_settings_submitted": "1", "show_world_map": "on", "council_mode": "agency"},
        )
        s = SiteSettings.load()
        self.assertFalse(s.show_star_map)   # absent in POST => turned off
        self.assertTrue(s.show_world_map)   # present => stays on
        # Charter is not part of the core form, so it must be preserved.
        self.assertEqual(s.charter_text, "THE CHARTER")

    def test_ship_budget_form_is_isolated_and_functional(self):
        # Its own form: absent checkbox => off, present => on; never touches core.
        self.client.post(self.url, {"ship_budget_submitted": "1"})
        self.assertFalse(SiteSettings.load().enforce_ship_slot_budget)
        self.client.post(
            self.url, {"ship_budget_submitted": "1", "enforce_ship_slot_budget": "on"}
        )
        s = SiteSettings.load()
        self.assertTrue(s.enforce_ship_slot_budget)
        self.assertTrue(s.show_star_map)  # core untouched

    def test_charter_only_written_when_present(self):
        # A core save without a charter field must not blank the charter...
        self.client.post(self.url, {"core_settings_submitted": "1"})
        self.assertEqual(SiteSettings.load().charter_text, "THE CHARTER")
        # ...but an explicit charter_text (e.g. from admin) is honoured.
        self.client.post(
            self.url, {"core_settings_submitted": "1", "charter_text": "NEW CHARTER"}
        )
        self.assertEqual(SiteSettings.load().charter_text, "NEW CHARTER")


class MediaServingTests(TestCase):
    """v0.15.61: uploads under MEDIA_ROOT must be served even with DEBUG=False.

    Production runs with DJANGO_DEBUG=False, and Django's ``static()`` URL helper
    registers no route in that case — every portrait and news image 404'd.
    """

    def test_media_file_is_served_with_debug_off(self):
        import tempfile
        from pathlib import Path
        from django.test import override_settings

        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "news").mkdir()
            (Path(tmp) / "news" / "pic.png").write_bytes(b"\x89PNG-not-really")
            with override_settings(DEBUG=False, MEDIA_ROOT=tmp):
                resp = self.client.get("/media/news/pic.png")
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(b"".join(resp.streaming_content), b"\x89PNG-not-really")
                self.assertEqual(self.client.get("/media/news/missing.png").status_code, 404)
