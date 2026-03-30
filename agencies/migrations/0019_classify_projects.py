"""Data migration: add classified=True to all existing agency projects."""

from django.db import migrations


def classify_all_projects(apps, schema_editor):
    Agency = apps.get_model("agencies", "Agency")
    for agency in Agency.objects.all():
        if agency.projects:
            updated = False
            for project in agency.projects:
                if isinstance(project, dict) and "classified" not in project:
                    project["classified"] = True
                    updated = True
            if updated:
                agency.save(update_fields=["projects"])


class Migration(migrations.Migration):
    dependencies = [
        ("agencies", "0018_add_zero_day_pool"),
    ]

    operations = [
        migrations.RunPython(classify_all_projects, migrations.RunPython.noop),
    ]
