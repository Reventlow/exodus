import json

import agencies.models
from django.db import migrations, models


def convert_alliance_to_json(apps, schema_editor):
    """Convert existing alliance CharField values to valid JSON strings.

    SQLite enforces JSON_VALID on JSONField columns, so we must ensure all
    existing rows contain valid JSON before the AlterField operation rebuilds
    the table.
    """
    Agency = apps.get_model("agencies", "Agency")
    default = {"countries": [], "companies": [], "organizations": []}

    for agency in Agency.objects.all():
        raw = agency.alliance
        # Already a dict (shouldn't happen with CharField, but be safe)
        if isinstance(raw, dict):
            continue
        # Empty or whitespace-only string → use default
        if not raw or not raw.strip():
            agency.alliance = json.dumps(default)
        else:
            # Try parsing as JSON first
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    continue  # already valid JSON dict
            except (json.JSONDecodeError, TypeError):
                pass
            # Plain string like "NATO" → put it in organizations
            agency.alliance = json.dumps({
                "countries": [],
                "companies": [],
                "organizations": [raw.strip()],
            })
        agency.save(update_fields=["alliance"])


class Migration(migrations.Migration):

    dependencies = [
        ("agencies", "0001_initial"),
    ]

    operations = [
        # Step 1: convert existing string values to valid JSON strings
        migrations.RunPython(
            convert_alliance_to_json,
            reverse_code=migrations.RunPython.noop,
        ),
        # Step 2: change the column type to JSONField
        migrations.AlterField(
            model_name="agency",
            name="alliance",
            field=models.JSONField(default=agencies.models.default_alliance),
        ),
    ]
