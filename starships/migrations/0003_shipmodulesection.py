"""Add ShipModuleSection + tier fields on ShipModule."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("starships", "0002_seed_catalogue"),
    ]

    operations = [
        migrations.CreateModel(
            name="ShipModuleSection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(max_length=60, unique=True)),
                ("name", models.CharField(max_length=120)),
                ("description", models.TextField(blank=True, default="")),
                ("order", models.IntegerField(default=0)),
            ],
            options={"ordering": ["order", "name"]},
        ),
        migrations.AddField(
            model_name="shipmodule",
            name="section",
            field=models.ForeignKey(
                blank=True,
                help_text="Optional tier family. Null = standalone module.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="modules",
                to="starships.shipmodulesection",
            ),
        ),
        migrations.AddField(
            model_name="shipmodule",
            name="level",
            field=models.IntegerField(
                default=0,
                help_text="Tier within the section (1-5). Ignored when section is null.",
            ),
        ),
    ]
