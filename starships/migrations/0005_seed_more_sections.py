"""Seed eight more tiered module sections on top of the v0.13.9 set.

Adds:
  - Titan Cannon (L1-L5)          — restricted to a new "titan" ship type
  - Bridge (L1-L5)                — command & control tier family
  - Anti-Small-Craft Missiles L1-5
  - Torpedo Launcher L1-5
  - Drone Bay L1-5                — restricted to carrier + titan
  - Solo Craft Bay L1-5           — restricted to carrier + titan
  - Manoeuvring Thrusters L1-5    — propulsion, agility booster
  - Sublight Engines L1-5         — propulsion, provides_sublight on every tier

Also adds a new "titan" ShipType so Titan Cannons have somewhere to
live. GMs can rename, retune, or delete any of these from Settings.

Idempotent via update_or_create.
"""

from django.db import migrations


NEW_SHIP_TYPES = [
    {
        "key": "titan",
        "name": "Titan",
        "description": "Capital-scale dreadnaught. Bigger than a dreadnaught, rarer than a dream.",
        "default_slot_budget": 32,
        "min_size": 9, "max_size": 12,
        "base_crew": 400, "base_energy": 30, "base_maintenance": 30,
        "order": 8,
    },
]


NEW_SECTIONS = [
    {"key": "titan_cannon",        "name": "Titan Cannon",
     "description": "Capital-class spinal weapons for titans and heavy dreadnaughts.",
     "order": 6},
    {"key": "bridge",              "name": "Bridge",
     "description": "Command and control centre tier family.",
     "order": 7},
    {"key": "anti_small_missiles", "name": "Anti-Small-Craft Missiles",
     "description": "Interceptor missile launchers tuned against fighters and drones.",
     "order": 8},
    {"key": "torpedoes",           "name": "Torpedo Launcher",
     "description": "Heavy standoff torpedo launchers.",
     "order": 9},
    {"key": "drone_bay_tier",      "name": "Drone Bay",
     "description": "Tiered drone hangar and deployment bay.",
     "order": 10},
    {"key": "solo_craft_bay",      "name": "Solo Craft Bay",
     "description": "Launch and recovery deck for solo fighters.",
     "order": 11},
    {"key": "manoeuvring_thrusters", "name": "Manoeuvring Thrusters",
     "description": "Attitude and fine-manoeuvre thrusters; stack with a sublight drive for agility.",
     "order": 12},
    {"key": "sublight_engines",    "name": "Sublight Engines",
     "description": "Primary in-system reaction drives. Every tier provides sublight capability.",
     "order": 13},
]


# Each entry lists five tier names + per-level scaling curves.
TIERED = [
    {
        "section": "titan_cannon",
        "category": "weapons",
        "names": [
            "Light Mass Driver",
            "Heavy Mass Driver",
            "Plasma Lance",
            "Dual Plasma Lance",
            "Godbreaker Cannon",
        ],
        "slot": [4, 5, 6, 7, 8],
        "crew": [8, 12, 16, 22, 30],
        "energy": [6, 9, 12, 16, 22],
        "maint": [4, 5, 6, 8, 10],
        "min_hull": [8, 8, 9, 9, 10],
        "xp": [10, 14, 20, 28, 40],
        "restricted_to_types": ["titan", "dreadnaught"],
    },
    {
        "section": "bridge",
        "category": "command",
        "names": [
            "Standard Bridge",
            "Tactical Bridge",
            "Combat Information Centre",
            "Fleet Bridge",
            "Sovereign Bridge",
        ],
        "slot": [1, 1, 2, 2, 3],
        "crew": [4, 6, 9, 12, 16],
        "energy": [1, 2, 2, 3, 4],
        "maint": [1, 2, 2, 3, 4],
        "min_hull": [2, 3, 4, 5, 6],
        "xp": [2, 4, 6, 10, 14],
        "restricted_to_types": [],
    },
    {
        "section": "anti_small_missiles",
        "category": "weapons",
        "names": [
            "AAM Rack",
            "Interceptor Pod",
            "Seeker Array",
            "Hydra Launcher",
            "Screamer Salvo",
        ],
        "slot": [1, 1, 2, 2, 3],
        "crew": [1, 2, 2, 3, 4],
        "energy": [1, 2, 2, 3, 4],
        "maint": [1, 1, 2, 2, 3],
        "min_hull": [2, 3, 3, 4, 5],
        "xp": [2, 4, 6, 9, 12],
        "restricted_to_types": [],
    },
    {
        "section": "torpedoes",
        "category": "weapons",
        "names": [
            "Single Torpedo Tube",
            "Twin Torpedo Tube",
            "Heavy Torpedo Launcher",
            "Swarm Torpedo Launcher",
            "Annihilator Tube",
        ],
        "slot": [2, 2, 3, 4, 5],
        "crew": [3, 4, 6, 9, 12],
        "energy": [2, 2, 3, 5, 7],
        "maint": [2, 2, 3, 4, 5],
        "min_hull": [3, 4, 5, 6, 7],
        "xp": [4, 6, 9, 13, 18],
        "restricted_to_types": [],
    },
    {
        "section": "drone_bay_tier",
        "category": "hangar",
        "names": [
            "Service Drone Bay",
            "Combat Drone Bay",
            "Heavy Drone Bay",
            "Drone Mothership Deck",
            "Autonomous Swarm Hive",
        ],
        "slot": [2, 3, 4, 5, 6],
        "crew": [4, 6, 9, 12, 16],
        "energy": [2, 3, 4, 6, 8],
        "maint": [2, 3, 4, 5, 6],
        "min_hull": [5, 6, 7, 8, 9],
        "xp": [4, 7, 11, 16, 22],
        "restricted_to_types": ["carrier", "titan"],
    },
    {
        "section": "solo_craft_bay",
        "category": "hangar",
        "names": [
            "Single Launch Tube",
            "Twin Launch Tube",
            "Fighter Hangar",
            "Strike Wing Bay",
            "Carrier Wing Deck",
        ],
        "slot": [3, 4, 5, 6, 8],
        "crew": [6, 10, 15, 22, 30],
        "energy": [3, 4, 6, 8, 11],
        "maint": [3, 4, 5, 7, 9],
        "min_hull": [6, 6, 7, 8, 9],
        "xp": [5, 9, 14, 20, 28],
        "restricted_to_types": ["carrier", "titan"],
    },
    {
        "section": "manoeuvring_thrusters",
        "category": "propulsion",
        "names": [
            "Basic Thrusters",
            "Trim Thrusters",
            "Vector Thrusters",
            "Reaction Jets",
            "Agility Array",
        ],
        "slot": [1, 1, 1, 2, 2],
        "crew": [0, 1, 1, 2, 2],
        "energy": [1, 1, 2, 2, 3],
        "maint": [1, 1, 1, 2, 2],
        "min_hull": [1, 1, 2, 3, 4],
        "xp": [1, 2, 4, 6, 9],
        "restricted_to_types": [],
    },
    {
        "section": "sublight_engines",
        "category": "propulsion",
        "names": [
            "Standard Reaction Drive",
            "Enhanced Reaction Drive",
            "High-Output Drive",
            "Pulse Drive",
            "Overdrive Core",
        ],
        "slot": [1, 2, 2, 3, 3],
        "crew": [1, 2, 2, 3, 4],
        "energy": [2, 3, 4, 5, 7],
        "maint": [1, 2, 2, 3, 4],
        "min_hull": [1, 2, 3, 4, 5],
        "xp": [2, 4, 6, 9, 13],
        "restricted_to_types": [],
        "provides_sublight": True,
    },
]


def seed(apps, schema_editor):
    ShipType = apps.get_model("starships", "ShipType")
    ShipModuleSection = apps.get_model("starships", "ShipModuleSection")
    ShipModule = apps.get_model("starships", "ShipModule")

    # Ship types
    for row in NEW_SHIP_TYPES:
        ShipType.objects.update_or_create(
            key=row["key"],
            defaults={k: v for k, v in row.items() if k != "key"},
        )

    # Sections
    section_map = {}
    for row in NEW_SECTIONS:
        obj, _ = ShipModuleSection.objects.update_or_create(
            key=row["key"],
            defaults={k: v for k, v in row.items() if k != "key"},
        )
        section_map[row["key"]] = obj

    # Tiered modules
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
                    "restricted_to_types": spec.get("restricted_to_types") or [],
                    "provides_sublight": bool(spec.get("provides_sublight", False)),
                    "provides_ftl": bool(spec.get("provides_ftl", False)),
                    "section": section,
                    "level": level,
                    "order": level,
                },
            )


def unseed(apps, schema_editor):
    ShipType = apps.get_model("starships", "ShipType")
    ShipModuleSection = apps.get_model("starships", "ShipModuleSection")
    ShipModule = apps.get_model("starships", "ShipModule")

    # Delete modules first, then sections, then the new ship type.
    for spec in TIERED:
        for idx in range(len(spec["names"])):
            ShipModule.objects.filter(key=f"{spec['section']}_l{idx + 1}").delete()
    ShipModuleSection.objects.filter(
        key__in=[s["key"] for s in NEW_SECTIONS],
    ).delete()
    ShipType.objects.filter(
        key__in=[t["key"] for t in NEW_SHIP_TYPES],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("starships", "0004_seed_sections"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
