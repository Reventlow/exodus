"""Add enforce_ship_slot_budget toggle to SiteSettings for the starships app."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("exodus", "0012_sitesettings_council_mode_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="enforce_ship_slot_budget",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "If true, the starship class editor rejects designs "
                    "that exceed their ShipType's slot budget. If false, "
                    "it only warns — useful for sketching in-progress "
                    "designs."
                ),
            ),
        ),
    ]
