"""Add per-class base-building unlock flags to SiteSettings."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("exodus", "0014_sitesettings_show_starships"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="class_unlock_flags",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Per-class base-building unlock flags. If a class key is "
                    "True, items flagged required_class=<that class> become "
                    "available to all characters. Use when the campaign has "
                    "no character of that class so the mechanics are not "
                    "inaccessible."
                ),
            ),
        ),
    ]
