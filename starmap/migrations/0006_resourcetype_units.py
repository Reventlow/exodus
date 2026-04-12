"""Add absolute-quantity unit fields to ResourceType.

Resource values on StarSystem.resources become integers in these units
instead of 0-100 percentages. Scan uncertainty is expressed as +/- brackets
in the same unit.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("starmap", "0005_planet"),
    ]

    operations = [
        migrations.AddField(
            model_name="resourcetype",
            name="unit_label",
            field=models.CharField(
                default="units",
                help_text="Gameplay unit, e.g. 'carrier loads', 'kt ore', 'canisters'.",
                max_length=50,
            ),
        ),
        migrations.AddField(
            model_name="resourcetype",
            name="unit_description",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Human-readable meaning of one unit, e.g. '1 load = one drone carrier refuel'.",
                max_length=200,
            ),
        ),
        migrations.AddField(
            model_name="resourcetype",
            name="typical_min",
            field=models.IntegerField(
                default=0,
                help_text="Galaxy-wide low end used by the procedural seeder.",
            ),
        ),
        migrations.AddField(
            model_name="resourcetype",
            name="typical_max",
            field=models.IntegerField(
                default=100,
                help_text="Galaxy-wide high end used by the procedural seeder.",
            ),
        ),
        migrations.AddField(
            model_name="resourcetype",
            name="rarity_weight",
            field=models.FloatField(
                default=1.0,
                help_text="0.0-1.0 probability this resource is present in a given system.",
            ),
        ),
        migrations.AddField(
            model_name="resourcetype",
            name="scan_bracket_wide",
            field=models.IntegerField(
                default=40,
                help_text="+/- uncertainty in units at scan level 1 (survey).",
            ),
        ),
        migrations.AddField(
            model_name="resourcetype",
            name="scan_bracket_narrow",
            field=models.IntegerField(
                default=15,
                help_text="+/- uncertainty in units at scan level 2 (focused). Level 3 is exact.",
            ),
        ),
    ]
