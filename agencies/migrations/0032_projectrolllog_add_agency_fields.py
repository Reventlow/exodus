"""No-op.

0031_projectrolllog already creates ProjectRollLog with the agency FK,
project_index, project_name, and nullable assignment in their final form,
so the AddField / AlterField operations this migration originally held
would crash on a fresh DB with 'duplicate column name'. Kept as an empty
migration to preserve the dependency chain for 0033_councilitem_predicted_votes
and for databases that already recorded it.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("agencies", "0031_projectrolllog"),
    ]

    operations = []
