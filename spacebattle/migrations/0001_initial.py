"""Initial schema for the spacebattle app.

Three models:
  1. Battle              — top-level engagement
  2. BattleParticipant   — ship instance on the grid (FK → starships.Starship)
  3. BattleLog           — append-only action log
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("starships", "0005_seed_more_sections"),
    ]

    operations = [
        migrations.CreateModel(
            name="Battle",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("game_date", models.CharField(blank=True, default="", help_text="In-game date string (matches the dispatch game_date field).", max_length=100)),
                (
                    "status",
                    models.CharField(
                        choices=[("setup", "Setup"), ("active", "Active"), ("concluded", "Concluded")],
                        default="setup",
                        max_length=20,
                    ),
                ),
                ("grid_width", models.IntegerField(default=20, help_text="Axial hex grid width. Configurable per battle; canvas caps around 40.")),
                ("grid_height", models.IntegerField(default=15, help_text="Axial hex grid height.")),
                ("round_number", models.IntegerField(default=1, help_text="Current combat round — one full pass through the initiative order.")),
                ("active_participant_index", models.IntegerField(default=0, help_text="Index into initiative_order identifying whose turn it is.")),
                (
                    "initiative_order",
                    models.JSONField(
                        blank=True, default=list,
                        help_text="List of BattleParticipant ids in descending initiative order for the current round.",
                    ),
                ),
                ("notes", models.TextField(blank=True, default="")),
                (
                    "metadata",
                    models.JSONField(
                        blank=True, default=dict,
                        help_text="Free-form JSON for extensions (terrain, objectives, house rules).",
                    ),
                ),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_battles",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="BattleParticipant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "side",
                    models.CharField(
                        choices=[("players", "Players"), ("enemies", "Enemies"), ("neutral", "Neutral")],
                        default="neutral",
                        max_length=20,
                    ),
                ),
                ("q", models.IntegerField(default=0, help_text="Axial hex q coordinate.")),
                ("r", models.IntegerField(default=0, help_text="Axial hex r coordinate.")),
                ("facing", models.IntegerField(default=0, help_text="Hex edge facing, 0-5. 0 = east, clockwise.")),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Active"), ("damaged", "Damaged"), ("disabled", "Disabled"), ("destroyed", "Destroyed")],
                        default="active",
                        max_length=20,
                    ),
                ),
                ("initiative_roll", models.IntegerField(blank=True, null=True, help_text="Raw d10 roll for this round before bonuses.")),
                ("initiative_result", models.IntegerField(blank=True, null=True, help_text="Final initiative after applying ship type bonus.")),
                ("token_color", models.CharField(blank=True, default="", help_text="Override colour for the canvas token. Empty = side default.", max_length=20)),
                ("token_icon", models.CharField(blank=True, default="", help_text="Unicode glyph or short label rendered on the token.", max_length=20)),
                ("notes", models.TextField(blank=True, default="")),
                ("position_order", models.IntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "battle",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="participants",
                        to="spacebattle.battle",
                    ),
                ),
                (
                    "starship",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="battle_participations",
                        to="starships.starship",
                    ),
                ),
            ],
            options={"ordering": ["battle", "position_order", "id"]},
        ),
        migrations.AddConstraint(
            model_name="battleparticipant",
            constraint=models.UniqueConstraint(
                fields=("battle", "starship"),
                name="unique_starship_per_battle",
            ),
        ),
        migrations.CreateModel(
            name="BattleLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("round_number", models.IntegerField(default=1)),
                (
                    "action_type",
                    models.CharField(
                        choices=[
                            ("system", "System"),
                            ("note", "GM Note"),
                            ("initiative", "Initiative"),
                            ("turn_advance", "Turn Advance"),
                            ("move", "Move"),
                            ("fire", "Fire"),
                            ("damage", "Damage"),
                            ("status_change", "Status Change"),
                            ("rollback", "Rollback"),
                        ],
                        default="note",
                        max_length=30,
                    ),
                ),
                (
                    "data",
                    models.JSONField(
                        blank=True, default=dict,
                        help_text="Action-specific payload: coordinates, weapon key, damage deltas, etc.",
                    ),
                ),
                ("message", models.TextField(blank=True, default="")),
                ("is_reverted", models.BooleanField(default=False, help_text="Set by the Release G rollback handler when an entry has been undone.")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "battle",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="log_entries",
                        to="spacebattle.battle",
                    ),
                ),
                (
                    "actor_participant",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="log_entries",
                        to="spacebattle.battleparticipant",
                    ),
                ),
            ],
            options={"ordering": ["battle", "id"]},
        ),
    ]
