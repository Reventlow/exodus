"""Terrain, reusable terrain templates, and full battle maps."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("spacebattle", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="BattleTerrain",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("q", models.IntegerField()),
                ("r", models.IntegerField()),
                (
                    "terrain_type",
                    models.CharField(
                        choices=[
                            ("asteroid", "Asteroid Field"),
                            ("nebula", "Nebula"),
                            ("debris", "Debris Field"),
                            ("planet", "Planet / Moon"),
                            ("sun", "Star / Sun Hazard"),
                            ("gravity_well", "Gravity Well"),
                            ("minefield", "Minefield"),
                            ("station", "Station / Platform"),
                            ("zone", "Scenario Zone"),
                            ("custom", "Custom"),
                        ],
                        default="asteroid",
                        max_length=30,
                    ),
                ),
                ("display_name", models.CharField(blank=True, default="", max_length=200)),
                ("color", models.CharField(blank=True, default="", help_text="Override hex colour. Empty = default per terrain type.", max_length=20)),
                ("icon", models.CharField(blank=True, default="", help_text="Override unicode glyph. Empty = default per terrain type.", max_length=20)),
                ("notes", models.TextField(blank=True, default="")),
                (
                    "metadata",
                    models.JSONField(
                        blank=True, default=dict,
                        help_text="Rule hooks (blocks_los, movement_cost, damage_per_turn) — reserved.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "battle",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="terrain_features",
                        to="spacebattle.battle",
                    ),
                ),
            ],
            options={"ordering": ["battle", "r", "q"]},
        ),
        migrations.AddConstraint(
            model_name="battleterrain",
            constraint=models.UniqueConstraint(
                fields=("battle", "q", "r"),
                name="unique_terrain_per_hex",
            ),
        ),
        migrations.CreateModel(
            name="TerrainTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200, unique=True)),
                ("description", models.TextField(blank=True, default="")),
                (
                    "hexes",
                    models.JSONField(
                        blank=True, default=list,
                        help_text="List of {q, r, terrain_type, display_name?, color?, icon?} with q/r as offsets from the template origin (0,0).",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True, null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="terrain_templates",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="BattleMap",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200, unique=True)),
                ("description", models.TextField(blank=True, default="")),
                ("grid_width", models.IntegerField(default=20)),
                ("grid_height", models.IntegerField(default=15)),
                (
                    "terrain",
                    models.JSONField(
                        blank=True, default=list,
                        help_text="Absolute-coordinate terrain list: [{q, r, terrain_type, display_name?, color?, icon?, notes?}].",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True, null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="battle_maps",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["name"]},
        ),
    ]
