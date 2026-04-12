"""Add show_starships visibility toggle to SiteSettings."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("exodus", "0013_sitesettings_enforce_ship_slot_budget"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="show_starships",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Show STARSHIPS link in navigation and let players "
                    "open the /starships/ page."
                ),
            ),
        ),
    ]
