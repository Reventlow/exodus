"""Re-add Fringe Science Lab facility type to BaseConfig.

Migration 0029 originally added it, but the singleton was subsequently
overwritten via the admin API (PUT /api/base-config/) and the entry was
dropped. This migration re-inserts it idempotently.
"""

from django.db import migrations


FRINGE_LAB = {
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


def reseed_fringe_lab(apps, schema_editor):
    BaseConfig = apps.get_model("agencies", "BaseConfig")
    for config in BaseConfig.objects.all():
        facilities = list(config.facility_types or [])
        if not any(f.get("key") == "fringe_lab" for f in facilities):
            facilities.append(FRINGE_LAB)
            config.facility_types = facilities
            config.save()


def noop(apps, schema_editor):
    # Reverse is intentionally a no-op — 0029 is the authoritative add
    # and reversing this migration should not strip the entry.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("agencies", "0033_councilitem_predicted_votes"),
    ]

    operations = [
        migrations.RunPython(reseed_fringe_lab, noop),
    ]
