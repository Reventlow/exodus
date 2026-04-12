"""Initial schema for the starships app.

Six models in dependency order:
  1. ShipType         — hull catalogue (no FKs)
  2. ShipModule       — module catalogue (no FKs)
  3. Fleet            — FK → agencies.Agency
  4. StarshipClass    — FK → ShipType, FK → agencies.Agency (nullable)
  5. ClassModule      — through M2M: FK → StarshipClass, FK → ShipModule
  6. Starship         — FK → StarshipClass, Agency, Fleet, Base, StarSystem
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("agencies", "0033_councilitem_predicted_votes"),
        ("starmap", "0007_seed_resource_types"),
    ]

    operations = [
        migrations.CreateModel(
            name="ShipType",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(max_length=50, unique=True)),
                ("name", models.CharField(max_length=100)),
                ("description", models.TextField(blank=True, default="")),
                ("default_slot_budget", models.IntegerField(default=4, help_text="Module slots available before size/module adjustments.")),
                ("min_size", models.IntegerField(default=1)),
                ("max_size", models.IntegerField(default=10)),
                ("base_crew", models.IntegerField(default=0)),
                ("base_energy", models.IntegerField(default=0)),
                ("base_maintenance", models.IntegerField(default=0)),
                ("order", models.IntegerField(default=0)),
            ],
            options={"ordering": ["order", "name"]},
        ),
        migrations.CreateModel(
            name="ShipModule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(max_length=60, unique=True)),
                ("name", models.CharField(max_length=120)),
                ("description", models.TextField(blank=True, default="")),
                (
                    "category",
                    models.CharField(
                        max_length=20,
                        default="special",
                        choices=[
                            ("propulsion", "Propulsion"),
                            ("power", "Power"),
                            ("weapons", "Weapons"),
                            ("defense", "Defense"),
                            ("sensors", "Sensors"),
                            ("quarters", "Crew Quarters"),
                            ("cargo", "Cargo"),
                            ("hangar", "Hangar / Bay"),
                            ("command", "Command & Control"),
                            ("special", "Special"),
                        ],
                    ),
                ),
                ("slot_cost", models.IntegerField(default=1)),
                ("crew_delta", models.IntegerField(default=0, help_text="Change to required crew. Negative = automated module.")),
                ("energy_delta", models.IntegerField(default=0)),
                ("maintenance_delta", models.IntegerField(default=0)),
                ("provides_sublight", models.BooleanField(default=False, help_text="Class needs at least one module with this flag to manoeuvre.")),
                ("provides_ftl", models.BooleanField(default=False, help_text="Class needs this for interstellar travel.")),
                ("min_hull_size", models.IntegerField(default=1, help_text="Smallest hull that can fit this module.")),
                ("restricted_to_types", models.JSONField(blank=True, default=list, help_text="List of ShipType.key values; empty = available to all.")),
                ("build_cost_xp_delta", models.IntegerField(default=0, help_text="XP this module adds to the class's build cost.")),
                ("xp_cost", models.IntegerField(default=0, help_text="Research/unlock cost for this module (one-off).")),
                ("order", models.IntegerField(default=0)),
            ],
            options={"ordering": ["category", "order", "name"]},
        ),
        migrations.CreateModel(
            name="Fleet",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("commander", models.CharField(blank=True, default="", help_text="Character name commanding this fleet.", max_length=200)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "agency",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="fleets",
                        to="agencies.agency",
                    ),
                ),
            ],
            options={"ordering": ["agency", "name"]},
        ),
        migrations.CreateModel(
            name="StarshipClass",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("size", models.IntegerField(default=1, help_text="Hull size. Must fall within the ShipType's min/max.")),
                ("description", models.TextField(blank=True, default="")),
                ("is_locked", models.BooleanField(default=False, help_text="Locked classes cannot be edited; used once a design is finalised.")),
                ("build_cost_xp", models.IntegerField(default=0, help_text="XP cost to commission one hull of this class.")),
                ("build_required_successes", models.IntegerField(default=5, help_text="Successes needed on construction rolls (like FTL projects).")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "ship_type",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="classes",
                        to="starships.shiptype",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        help_text="Null = GM-shared class available to all agencies.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="starship_classes",
                        to="agencies.agency",
                    ),
                ),
            ],
            options={"ordering": ["name"], "verbose_name_plural": "starship classes"},
        ),
        migrations.CreateModel(
            name="ClassModule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity", models.IntegerField(default=1)),
                ("notes", models.TextField(blank=True, default="")),
                ("position", models.IntegerField(default=0, help_text="Render order in the class editor.")),
                (
                    "module",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="class_installs",
                        to="starships.shipmodule",
                    ),
                ),
                (
                    "starship_class",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="class_modules",
                        to="starships.starshipclass",
                    ),
                ),
            ],
            options={"ordering": ["position", "id"]},
        ),
        migrations.AddField(
            model_name="starshipclass",
            name="modules",
            field=models.ManyToManyField(
                related_name="classes",
                through="starships.ClassModule",
                to="starships.shipmodule",
            ),
        ),
        migrations.CreateModel(
            name="Starship",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("hull_number", models.CharField(blank=True, default="", max_length=50)),
                (
                    "status",
                    models.CharField(
                        max_length=30,
                        default="under_construction",
                        choices=[
                            ("under_construction", "Under Construction"),
                            ("active", "Active"),
                            ("damaged", "Damaged"),
                            ("in_dock", "In Dock"),
                            ("decommissioned", "Decommissioned"),
                            ("lost", "Lost"),
                        ],
                    ),
                ),
                ("current_crew", models.IntegerField(default=0, help_text="Filled crew slots; compare vs class required_crew.")),
                ("maintenance_state", models.IntegerField(default=100, help_text="Percentage. 0 = wreck, 100 = pristine.")),
                ("current_successes", models.IntegerField(default=0)),
                ("commissioned_at", models.DateTimeField(blank=True, null=True)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "starship_class",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="hulls",
                        to="starships.starshipclass",
                    ),
                ),
                (
                    "agency",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="starships",
                        to="agencies.agency",
                    ),
                ),
                (
                    "fleet",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="ships",
                        to="starships.fleet",
                    ),
                ),
                (
                    "build_assigned_base",
                    models.ForeignKey(
                        blank=True,
                        help_text="Shipyard/base currently constructing this hull.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="building_ships",
                        to="agencies.base",
                    ),
                ),
                (
                    "location",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="docked_ships",
                        to="starmap.starsystem",
                    ),
                ),
            ],
            options={"ordering": ["agency", "name"]},
        ),
    ]
