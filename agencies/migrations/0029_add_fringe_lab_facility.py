"""Add Fringe Science Lab facility type to BaseConfig."""

from django.db import migrations


def add_fringe_lab(apps, schema_editor):
    BaseConfig = apps.get_model("agencies", "BaseConfig")
    fringe_lab = {
        "key": "fringe_lab",
        "name": "Fringe Science Lab",
        "required_class": "science",
        "levels": [
            {
                "level": 1,
                "name": "Fringe Lab",
                "exp": 15,
                "size": 5,
                "description": (
                    "A laboratory operating on the bleeding edge of science — "
                    "experimental physics, alternate biology, consciousness research. "
                    "Required to enable fringe effects on projects assigned to this base. "
                    "Requires the Fringe Science Labs pulling string to build."
                ),
            },
        ],
    }
    for config in BaseConfig.objects.all():
        facilities = config.facility_types or []
        if not any(f.get("key") == "fringe_lab" for f in facilities):
            facilities.append(fringe_lab)
            config.facility_types = facilities
            config.save()


def remove_fringe_lab(apps, schema_editor):
    BaseConfig = apps.get_model("agencies", "BaseConfig")
    for config in BaseConfig.objects.all():
        config.facility_types = [
            f for f in (config.facility_types or []) if f.get("key") != "fringe_lab"
        ]
        config.save()


class Migration(migrations.Migration):

    dependencies = [
        ("agencies", "0028_add_base_departments"),
    ]

    operations = [
        migrations.RunPython(add_fringe_lab, remove_fringe_lab),
    ]
