"""Seed a Battery Banks tier family (L1–L5).

Pure data migration. Battery banks raise a class's battery_power
capacity so shield generators, heavy guns, and titan cannons can
actually fire under the rules engine (when it ships). Higher tiers
cost more slots, crew, and maintenance.
"""

from django.db import migrations


SECTION = {
    "key": "battery_banks",
    "name": "Battery Banks",
    "description": "Energy storage modules. Raise combat battery capacity so shields and heavy guns can sustain fire.",
    "order": 14,
}


# (level, name, slot, crew, energy, maint, battery_delta, xp)
TIERS = [
    (1, "Basic Battery Bank",        1, 0, 0, 1,  3,  2),
    (2, "Standard Battery",          1, 1, 1, 1,  6,  4),
    (3, "Reinforced Battery Array",  2, 1, 1, 2, 10,  7),
    (4, "High-Capacity Battery",     2, 2, 2, 3, 15, 11),
    (5, "Fusion Battery Core",       3, 3, 2, 4, 25, 16),
]


def seed(apps, schema_editor):
    ShipModuleSection = apps.get_model("starships", "ShipModuleSection")
    ShipModule = apps.get_model("starships", "ShipModule")

    section, _ = ShipModuleSection.objects.update_or_create(
        key=SECTION["key"],
        defaults={k: v for k, v in SECTION.items() if k != "key"},
    )

    for level, name, slot, crew, energy, maint, bat_delta, xp in TIERS:
        key = f"battery_bank_l{level}"
        ShipModule.objects.update_or_create(
            key=key,
            defaults={
                "name": name,
                "description": f"Level {level} battery bank.",
                "category": "power",
                "slot_cost": slot,
                "crew_delta": crew,
                "energy_delta": energy,
                "maintenance_delta": maint,
                "battery_delta": bat_delta,
                "build_cost_xp_delta": xp,
                "min_hull_size": 1 if level < 3 else 2 if level < 5 else 4,
                "restricted_to_types": [],
                "section": section,
                "level": level,
                "order": level,
            },
        )


def unseed(apps, schema_editor):
    ShipModuleSection = apps.get_model("starships", "ShipModuleSection")
    ShipModule = apps.get_model("starships", "ShipModule")
    for level, *_ in TIERS:
        ShipModule.objects.filter(key=f"battery_bank_l{level}").delete()
    ShipModuleSection.objects.filter(key=SECTION["key"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("starships", "0009_weapon_stats"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
