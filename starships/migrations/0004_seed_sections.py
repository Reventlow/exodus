"""Seed ShipModuleSection catalogue and tiered modules.

Five sections, five tiers each. Each tier is a distinct ShipModule
row so GMs can balance slot cost / crew / power / build XP
independently per level. Inspired by the user's Fighter Guns example
(single auto cannon → twin auto cannons → gatling gun → twin gatling
guns → vengeance cannon).

Idempotent via update_or_create.
"""

from django.db import migrations


SECTIONS = [
    {"key": "fighter_guns", "name": "Fighter Guns",
     "description": "Short-range anti-fighter turrets and gun mounts.",
     "order": 1},
    {"key": "main_guns", "name": "Main Guns",
     "description": "Primary heavy weapon batteries for ship-to-ship combat.",
     "order": 2},
    {"key": "shields", "name": "Shields",
     "description": "Active deflector fields that absorb incoming energy.",
     "order": 3},
    {"key": "armour", "name": "Armour Plating",
     "description": "Passive ablative and composite hull plating.",
     "order": 4},
    {"key": "sensors", "name": "Sensor Suites",
     "description": "Detection, tracking, and countermeasure arrays.",
     "order": 5},
]


# Tiered module templates. Level is appended to key and delta values
# scale roughly linearly per tier. GMs retune from Settings once
# in-game experience calibrates the curve.
TIERED = [
    {
        "section": "fighter_guns",
        "category": "weapons",
        "names": [
            "Single Auto Cannon",
            "Twin Auto Cannons",
            "Gatling Gun",
            "Twin Gatling Guns",
            "Vengeance Cannon",
        ],
        "slot": [1, 1, 1, 2, 2],
        "crew": [1, 2, 2, 3, 4],
        "energy": [1, 1, 2, 3, 4],
        "maint": [1, 1, 2, 2, 3],
        "min_hull": [2, 2, 3, 3, 4],
        "xp": [2, 3, 5, 7, 10],
    },
    {
        "section": "main_guns",
        "category": "weapons",
        "names": [
            "Light Railgun",
            "Standard Railgun",
            "Heavy Railgun",
            "Particle Cannon",
            "Siege Beam",
        ],
        "slot": [2, 3, 3, 4, 5],
        "crew": [3, 5, 7, 9, 12],
        "energy": [2, 3, 4, 6, 8],
        "maint": [2, 3, 3, 4, 5],
        "min_hull": [4, 4, 5, 6, 7],
        "xp": [4, 6, 9, 12, 16],
    },
    {
        "section": "shields",
        "category": "defense",
        "names": [
            "Point Shield",
            "Deflector Screen",
            "Overlapping Fields",
            "Layered Bubble",
            "Fortress Shield",
        ],
        "slot": [1, 2, 2, 3, 4],
        "crew": [1, 2, 3, 4, 6],
        "energy": [2, 3, 5, 7, 10],
        "maint": [1, 2, 2, 3, 4],
        "min_hull": [3, 4, 4, 5, 6],
        "xp": [3, 5, 8, 11, 15],
    },
    {
        "section": "armour",
        "category": "defense",
        "names": [
            "Composite Plating",
            "Reactive Plating",
            "Ablative Armour",
            "Nanoforged Plating",
            "Adamant Hull",
        ],
        "slot": [1, 1, 2, 2, 3],
        "crew": [0, 0, 1, 1, 2],
        "energy": [0, 0, 0, 1, 1],
        "maint": [1, 2, 2, 3, 4],
        "min_hull": [2, 3, 4, 5, 6],
        "xp": [2, 3, 5, 8, 12],
    },
    {
        "section": "sensors",
        "category": "sensors",
        "names": [
            "Basic Sensor Array",
            "Long-Range Array",
            "Phased Sensor Grid",
            "Precog Suite",
            "Omniscan Array",
        ],
        "slot": [1, 1, 2, 2, 3],
        "crew": [1, 2, 2, 3, 4],
        "energy": [1, 1, 2, 3, 4],
        "maint": [1, 1, 2, 2, 3],
        "min_hull": [1, 2, 3, 4, 5],
        "xp": [2, 4, 6, 9, 13],
    },
]


def seed(apps, schema_editor):
    ShipModuleSection = apps.get_model("starships", "ShipModuleSection")
    ShipModule = apps.get_model("starships", "ShipModule")

    # Sections
    section_map = {}
    for row in SECTIONS:
        obj, _ = ShipModuleSection.objects.update_or_create(
            key=row["key"],
            defaults={k: v for k, v in row.items() if k != "key"},
        )
        section_map[row["key"]] = obj

    # Tiered modules — each level is its own ShipModule row.
    for spec in TIERED:
        section = section_map[spec["section"]]
        for idx, name in enumerate(spec["names"]):
            level = idx + 1
            key = f"{spec['section']}_l{level}"
            ShipModule.objects.update_or_create(
                key=key,
                defaults={
                    "name": name,
                    "description": f"Level {level} {section.name}.",
                    "category": spec["category"],
                    "slot_cost": spec["slot"][idx],
                    "crew_delta": spec["crew"][idx],
                    "energy_delta": spec["energy"][idx],
                    "maintenance_delta": spec["maint"][idx],
                    "min_hull_size": spec["min_hull"][idx],
                    "build_cost_xp_delta": spec["xp"][idx],
                    "section": section,
                    "level": level,
                    "order": level,
                },
            )


def unseed(apps, schema_editor):
    ShipModuleSection = apps.get_model("starships", "ShipModuleSection")
    ShipModule = apps.get_model("starships", "ShipModule")
    section_keys = [s["key"] for s in SECTIONS]
    # Delete modules first (FK constraint)
    for spec in TIERED:
        for idx in range(len(spec["names"])):
            ShipModule.objects.filter(key=f"{spec['section']}_l{idx + 1}").delete()
    ShipModuleSection.objects.filter(key__in=section_keys).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("starships", "0003_shipmodulesection"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
