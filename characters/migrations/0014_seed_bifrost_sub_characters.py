from django.db import migrations


# Players who each receive one Bifrost tactical sub-unit (by username).
SUB_OWNERS = ["kasper", "rasmus", "Christian"]
BIFROST_NAME = "Bifrost Union"
STARTING_XP = 25


def create_sub_characters(apps, schema_editor):
    """Seed one soldier sub-character per Bifrost player, idempotently.

    Each starts with 25 EARNED XP and is flagged ``is_sub_character`` so it is
    excluded from the agency XP economy (no transfers, no project/study XP, and
    never acts as the player's character for agency operations).
    """
    User = apps.get_model("auth", "User")
    Character = apps.get_model("characters", "Character")
    Agency = apps.get_model("agencies", "Agency")

    bifrost = (
        Agency.objects.filter(name=BIFROST_NAME).first()
        or Agency.objects.filter(is_player_agency=True).order_by("id").first()
    )

    for username in SUB_OWNERS:
        user = User.objects.filter(username=username).first()
        if not user:
            continue
        # Idempotent: skip if this player already has a sub-character.
        if Character.objects.filter(owner=user, is_sub_character=True).exists():
            continue
        Character.objects.create(
            owner=user,
            name="Bifrost Tactical Unit",
            character_class="soldier",
            concept="Bifrost soldier",
            is_sub_character=True,
            agency=bifrost,
            experience=STARTING_XP,
        )


def remove_sub_characters(apps, schema_editor):
    Character = apps.get_model("characters", "Character")
    User = apps.get_model("auth", "User")
    owner_ids = User.objects.filter(username__in=SUB_OWNERS).values_list("id", flat=True)
    Character.objects.filter(
        owner_id__in=list(owner_ids), is_sub_character=True
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("characters", "0013_character_agency_character_is_sub_character"),
        ("agencies", "0038_agency_scan_grant_agency_scan_usage_and_more"),
    ]

    operations = [
        migrations.RunPython(create_sub_characters, remove_sub_characters),
    ]
