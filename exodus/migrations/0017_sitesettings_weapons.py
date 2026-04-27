from django.db import migrations, models


def seed_weapons(apps, schema_editor):
    """Populate the weapons list on the singleton SiteSettings row with
    the canonical default catalogue if currently empty."""
    SiteSettings = apps.get_model("exodus", "SiteSettings")
    defaults = [
        {"name": "Knuckle Buster", "category": "melee"},
        {"name": "Knife", "category": "melee"},
        {"name": "Baton", "category": "melee"},
        {"name": "Taser (Contact)", "category": "melee"},
        {"name": "Chair", "category": "improvised"},
        {"name": "Bottle", "category": "improvised"},
        {"name": "Phone Book", "category": "improvised"},
        {"name": "Hammer", "category": "improvised"},
        {"name": "Hand Gun", "category": "firearm"},
        {"name": "Large Hand Gun", "category": "firearm"},
        {"name": "Sub Machine Gun", "category": "firearm"},
        {"name": "Assault Rifle", "category": "firearm"},
        {"name": "DMR", "category": "firearm"},
        {"name": "Shotgun", "category": "firearm"},
        {"name": "Twin-Barrel Shotgun", "category": "firearm"},
        {"name": "Auto Shotgun", "category": "firearm"},
        {"name": "Scoped Rifle", "category": "firearm"},
        {"name": "Taser (Cartridge)", "category": "firearm"},
        {"name": "Throwing Knife", "category": "thrown"},
        {"name": "Throwing Axe", "category": "thrown"},
    ]
    obj = SiteSettings.objects.filter(pk=1).first()
    if obj and not obj.weapons:
        obj.weapons = defaults
        obj.save(update_fields=["weapons"])


def reverse_seed(apps, schema_editor):
    """Reverse: clear the weapons list."""
    SiteSettings = apps.get_model("exodus", "SiteSettings")
    obj = SiteSettings.objects.filter(pk=1).first()
    if obj:
        obj.weapons = []
        obj.save(update_fields=["weapons"])


class Migration(migrations.Migration):

    dependencies = [
        ("exodus", "0016_sitesettings_tweaks"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="weapons",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    "List of {name, category} dicts. Categories: melee, "
                    "improvised, firearm, thrown. See "
                    "SiteSettings.default_weapons() for the seed catalogue."
                ),
            ),
        ),
        migrations.RunPython(seed_weapons, reverse_seed),
    ]
