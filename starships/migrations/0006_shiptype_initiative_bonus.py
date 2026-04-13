"""Add initiative_bonus to ShipType + seed values per canonical type.

Smaller hulls get a larger initiative bonus. Values are tunable from
Settings > Starships > Ship Types once the v0.14.x battle UI lands.
"""

from django.db import migrations, models


SEED_BONUSES = {
    "drone": 5,
    "solo": 4,
    "shuttle": 3,
    "cruiser": 1,
    "support": 1,
    "carrier": 0,
    "dreadnaught": -2,
    "titan": -3,
}


def seed_bonuses(apps, schema_editor):
    ShipType = apps.get_model("starships", "ShipType")
    for key, bonus in SEED_BONUSES.items():
        ShipType.objects.filter(key=key).update(initiative_bonus=bonus)


def unseed_bonuses(apps, schema_editor):
    ShipType = apps.get_model("starships", "ShipType")
    ShipType.objects.filter(
        key__in=list(SEED_BONUSES.keys()),
    ).update(initiative_bonus=0)


class Migration(migrations.Migration):

    dependencies = [
        ("starships", "0005_seed_more_sections"),
    ]

    operations = [
        migrations.AddField(
            model_name="shiptype",
            name="initiative_bonus",
            field=models.IntegerField(
                default=0,
                help_text="Bonus added to a d10 initiative roll in combat. Smaller ships get a larger bonus.",
            ),
        ),
        migrations.RunPython(seed_bonuses, unseed_bonuses),
    ]
