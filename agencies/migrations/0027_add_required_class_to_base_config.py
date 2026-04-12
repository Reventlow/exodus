"""Add required_class field to all BaseConfig JSON items for class-based visibility."""

from django.db import migrations


# Mapping of item key -> required_class
CLASS_MAP = {
    # Location types
    "official_building": "general",
    "estate": "fixer",
    "military_base": "soldier",
    "black_site": "soldier",
    # Location merits
    "armored": "soldier",
    "underwater": "engineer",
    "underground": "engineer",
    "extra_large": "general",
    "super_large": "general",
    "front": "fixer",
    # Facility types
    "aviation": "soldier",
    "auditorium": "fixer",
    "barracks": "soldier",
    "armory": "soldier",
    "brig": "soldier",
    "medical": "science",
    "computer_core": "engineer",
    "storage": "general",
    "workspace": "engineer",
    "hr_offboarding": "fixer",
    "engineering_project": "engineer",
    "science_project": "science",
    # Equipment types
    "short_med_planes": "soldier",
    "helicopters": "soldier",
    "long_range_planes": "soldier",
    "orbital_vehicles": "soldier",
    "internal_security": "general",
    "segmented_security": "soldier",
    "high_level_monitoring": "soldier",
    "external_defense": "soldier",
    "sam_ssm": "soldier",
}


def add_required_class(apps, schema_editor):
    BaseConfig = apps.get_model("agencies", "BaseConfig")
    for config in BaseConfig.objects.all():
        changed = False
        for field_name in ("location_types", "location_merits", "facility_types", "equipment_types"):
            items = getattr(config, field_name) or []
            for item in items:
                key = item.get("key")
                if key and "required_class" not in item:
                    item["required_class"] = CLASS_MAP.get(key, "general")
                    changed = True
            setattr(config, field_name, items)
        if changed:
            config.save()


def remove_required_class(apps, schema_editor):
    BaseConfig = apps.get_model("agencies", "BaseConfig")
    for config in BaseConfig.objects.all():
        for field_name in ("location_types", "location_merits", "facility_types", "equipment_types"):
            items = getattr(config, field_name) or []
            for item in items:
                item.pop("required_class", None)
            setattr(config, field_name, items)
        config.save()


class Migration(migrations.Migration):

    dependencies = [
        ("agencies", "0026_agencyftlproject_metadata"),
    ]

    operations = [
        migrations.RunPython(add_required_class, remove_required_class),
    ]
