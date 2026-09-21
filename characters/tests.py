"""Tests for sub-characters ("soldier units").

A sub-character is a secondary sheet a player runs while their main character is
otherwise engaged. It is deliberately walled off from the agency XP economy:

1. It can never act as the player's character for agency/project/base actions
   (``Character.main_for`` excludes it, even when it was edited most recently).
2. It cannot transfer XP to an agency.
3. It cannot be offered for assignment to agency projects.
4. Its EARNED XP is GM-controlled (owner edits are ignored).
"""

import json

from django.contrib.auth.models import User
from django.test import Client, TestCase

from agencies.models import Agency
from characters.models import Character


class SubCharacterTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="player", password="pw")
        self.agency = Agency.objects.create(name="Bifrost Union", is_player_agency=True)
        # Main character created first, then the sub-character edited last so
        # that the sub is the most-recently-updated row (the hijack scenario).
        self.main = Character.objects.create(owner=self.user, name="Main Op")
        self.sub = Character.objects.create(
            owner=self.user, name="Tactical Unit",
            is_sub_character=True, agency=self.agency, experience=25,
        )
        self.sub.concept = "touch to bump updated_at"
        self.sub.save()

        self.client = Client()
        self.client.force_login(self.user)

    def test_main_for_excludes_sub_even_when_edited_last(self):
        """The sub being most-recently-updated must not hijack agency actions."""
        self.assertEqual(Character.main_for(self.user), self.main)

    def test_sub_cannot_transfer_xp(self):
        resp = self.client.post(
            f"/api/characters/{self.sub.id}/transfer-xp/",
            data=json.dumps({"amount": 1, "agencyId": self.agency.id}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)
        # The agency must not have received any XP.
        self.agency.refresh_from_db()
        self.assertEqual(self.agency.experience, 0)

    def test_main_character_can_still_transfer_xp(self):
        self.main.experience = 5
        self.main.save(update_fields=["experience"])
        resp = self.client.post(
            f"/api/characters/{self.main.id}/transfer-xp/",
            data=json.dumps({"amount": 1, "agencyId": self.agency.id}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.agency.refresh_from_db()
        self.assertEqual(self.agency.experience, 10)

    def test_owner_cannot_inflate_sub_earned_xp(self):
        resp = self.client.put(
            f"/api/characters/{self.sub.id}/",
            data=json.dumps({"experience": 999}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.experience, 25)

    def test_sub_not_offered_for_project_assignment(self):
        from agencies.serializers import serialize_agency

        data = serialize_agency(self.agency, self.user)
        names = {c["name"] for c in data.get("assignableCharacters", [])}
        self.assertIn("Main Op", names)
        self.assertNotIn("Tactical Unit", names)

    def test_serializer_exposes_sub_flag(self):
        resp = self.client.get(f"/api/characters/{self.sub.id}/")
        payload = resp.json()
        self.assertTrue(payload["isSubCharacter"])
        self.assertEqual(payload["agencyName"], "Bifrost Union")
