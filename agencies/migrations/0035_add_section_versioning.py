"""Add optimistic-concurrency version fields.

Phase 2 of the multi-player concurrency fix:
  * Agency.section_versions — JSON map of {section_key: version} bumped
    on every successful section PATCH.
  * Base.version — monotonic counter bumped on every successful per-base
    section PATCH.

Both default cleanly on existing rows: empty dict for the JSON map,
0 for the integer counter.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("agencies", "0034_reseed_fringe_lab_facility"),
    ]

    operations = [
        migrations.AddField(
            model_name="agency",
            name="section_versions",
            field=models.JSONField(
                default=dict,
                help_text=(
                    "Per-section monotonic versions for optimistic concurrency on "
                    "agency-level PATCH endpoints."
                ),
            ),
        ),
        migrations.AddField(
            model_name="base",
            name="version",
            field=models.PositiveIntegerField(
                default=0,
                help_text=(
                    "Monotonic version for optimistic concurrency on per-base "
                    "PATCH endpoints."
                ),
            ),
        ),
    ]
