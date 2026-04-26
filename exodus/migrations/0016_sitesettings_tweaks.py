"""Add the ``tweaks`` JSON blob to SiteSettings for the Clearance Gate."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("exodus", "0015_sitesettings_class_unlock_flags"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="tweaks",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Login screen presentation. Keys: palette, backdrop, "
                    "map_intensity, show_radar, show_nodes, rain_style, "
                    "rain_density, rain_speed, scanlines, vignette, "
                    "show_rails, agency_name, op_codename. See "
                    "SiteSettings.default_tweaks() for defaults."
                ),
            ),
        ),
    ]
