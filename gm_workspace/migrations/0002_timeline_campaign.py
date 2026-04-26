from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gm_workspace", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TimelineEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=300)),
                ("description", models.TextField(blank=True, default="", help_text="Markdown")),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("session", "Session"),
                            ("plot", "Plot Beat"),
                            ("world", "World Event"),
                            ("note", "Note"),
                        ],
                        default="note",
                        max_length=20,
                    ),
                ),
                ("game_date", models.CharField(blank=True, default="", max_length=100, help_text="Human-readable in-game date (e.g. '13 May 2036').")),
                ("game_date_sort", models.DateTimeField(blank=True, null=True, help_text="Sortable datetime, auto-derived from game_date.")),
                ("tags", models.CharField(blank=True, default="", max_length=500, help_text="Comma-separated free-text tags.")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True, null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="created_timeline_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-game_date_sort", "-updated_at"]},
        ),
        migrations.CreateModel(
            name="CampaignSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("session_number", models.PositiveIntegerField(blank=True, null=True, help_text="Sequential session number. Leave blank for one-offs.")),
                ("title", models.CharField(max_length=300)),
                ("summary", models.TextField(blank=True, default="", help_text="Markdown recap")),
                ("played_at", models.DateField(blank=True, null=True, help_text="Real-world date the session was played.")),
                ("game_date", models.CharField(blank=True, default="", max_length=100, help_text="In-game date(s) covered by the session.")),
                ("tags", models.CharField(blank=True, default="", max_length=500, help_text="Comma-separated free-text tags.")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True, null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="created_campaign_sessions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["session_number", "-played_at"]},
        ),
    ]
