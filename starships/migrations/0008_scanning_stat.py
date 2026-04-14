"""Add scanning stat to ShipType and ShipModule + seed values.

Scanning represents detection range / sensor resolution. Support
ships and flagships get the best baseline; sensor modules push hard.
"""

from django.db import migrations, models


SHIP_TYPE_SCANNING = {
    "drone":       2,
    "solo":        3,
    "shuttle":     2,
    "cruiser":     3,
    "support":     4,   # science / survey role
    "carrier":     3,
    "dreadnaught": 4,
    "titan":       5,   # flagship sensor suite
}


MODULE_SCANNING_DELTAS = {
    # Standalone
    "sensor_array":           1,
    # Sensor Suites tier family
    "sensors_l1":             1,
    "sensors_l2":             2,
    "sensors_l3":             3,
    "sensors_l4":             5,
    "sensors_l5":             8,
}


def seed(apps, schema_editor):
    ShipType = apps.get_model("starships", "ShipType")
    ShipModule = apps.get_model("starships", "ShipModule")
    for key, scanning in SHIP_TYPE_SCANNING.items():
        ShipType.objects.filter(key=key).update(base_scanning=scanning)
    for key, delta in MODULE_SCANNING_DELTAS.items():
        ShipModule.objects.filter(key=key).update(scanning_delta=delta)


def unseed(apps, schema_editor):
    ShipType = apps.get_model("starships", "ShipType")
    ShipModule = apps.get_model("starships", "ShipModule")
    ShipType.objects.filter(key__in=SHIP_TYPE_SCANNING.keys()).update(base_scanning=2)
    ShipModule.objects.filter(key__in=MODULE_SCANNING_DELTAS.keys()).update(scanning_delta=0)


class Migration(migrations.Migration):

    dependencies = [
        ("starships", "0007_combat_stats"),
    ]

    operations = [
        migrations.AddField(
            model_name="shiptype",
            name="base_scanning",
            field=models.IntegerField(
                default=2,
                help_text="Sensor rating — detection range and resolution before modules.",
            ),
        ),
        migrations.AddField(
            model_name="shipmodule",
            name="scanning_delta",
            field=models.IntegerField(default=0, help_text="Added to sensor rating."),
        ),
        migrations.RunPython(seed, unseed),
    ]
