"""Seed canonical ship types and the starter module catalogue.

Idempotent via update_or_create so re-running is safe. Values are
round-numbers chosen to feel reasonable at the table; GMs can tune
every row from Settings > Starships once Release B ships the UI.
"""

from django.db import migrations


SHIP_TYPES = [
    {
        "key": "drone",
        "name": "Unmanned Drone",
        "description": "Single-purpose autonomous hull, no living crew.",
        "default_slot_budget": 2,
        "min_size": 1, "max_size": 2,
        "base_crew": 0, "base_energy": 1, "base_maintenance": 1,
        "order": 1,
    },
    {
        "key": "solo",
        "name": "Solo Ship",
        "description": "One-person fighter or courier.",
        "default_slot_budget": 4,
        "min_size": 1, "max_size": 3,
        "base_crew": 1, "base_energy": 2, "base_maintenance": 2,
        "order": 2,
    },
    {
        "key": "shuttle",
        "name": "Shuttle",
        "description": "Short-range crewed transport. Usually no FTL.",
        "default_slot_budget": 6,
        "min_size": 2, "max_size": 4,
        "base_crew": 2, "base_energy": 3, "base_maintenance": 3,
        "order": 3,
    },
    {
        "key": "cruiser",
        "name": "Cruiser",
        "description": "General-purpose warship. The backbone of most fleets.",
        "default_slot_budget": 12,
        "min_size": 4, "max_size": 7,
        "base_crew": 40, "base_energy": 8, "base_maintenance": 8,
        "order": 4,
    },
    {
        "key": "support",
        "name": "Support Ship",
        "description": "Tender, tanker, science vessel, or repair barge.",
        "default_slot_budget": 10,
        "min_size": 3, "max_size": 7,
        "base_crew": 25, "base_energy": 6, "base_maintenance": 6,
        "order": 5,
    },
    {
        "key": "carrier",
        "name": "Carrier",
        "description": "Drone or solo-ship platform with large hangar bays.",
        "default_slot_budget": 16,
        "min_size": 6, "max_size": 9,
        "base_crew": 80, "base_energy": 12, "base_maintenance": 12,
        "order": 6,
    },
    {
        "key": "dreadnaught",
        "name": "Dreadnaught",
        "description": "Flagship-class capital ship. Rare, expensive, politically sensitive.",
        "default_slot_budget": 24,
        "min_size": 8, "max_size": 10,
        "base_crew": 200, "base_energy": 20, "base_maintenance": 20,
        "order": 7,
    },
]


SHIP_MODULES = [
    # Propulsion
    {
        "key": "sublight_drive",
        "name": "Sublight Drive",
        "description": "Standard reaction drive for in-system manoeuvring.",
        "category": "propulsion",
        "slot_cost": 1,
        "crew_delta": 1, "energy_delta": 2, "maintenance_delta": 1,
        "provides_sublight": True,
        "min_hull_size": 1,
        "build_cost_xp_delta": 2,
        "order": 1,
    },
    {
        "key": "ftl_drive",
        "name": "FTL Drive",
        "description": "Displacement drive for interstellar jumps.",
        "category": "propulsion",
        "slot_cost": 2,
        "crew_delta": 2, "energy_delta": 5, "maintenance_delta": 3,
        "provides_ftl": True,
        "min_hull_size": 3,
        "build_cost_xp_delta": 8,
        "order": 2,
    },
    # Power
    {
        "key": "fusion_plant",
        "name": "Fusion Plant",
        "description": "Compact deuterium–tritium fusion reactor.",
        "category": "power",
        "slot_cost": 2,
        "crew_delta": 2, "energy_delta": -8, "maintenance_delta": 2,
        "min_hull_size": 2,
        "build_cost_xp_delta": 4,
        "order": 1,
    },
    {
        "key": "aux_generator",
        "name": "Auxiliary Generator",
        "description": "Small backup power plant; keeps lights on if the main plant trips.",
        "category": "power",
        "slot_cost": 1,
        "crew_delta": 0, "energy_delta": -3, "maintenance_delta": 1,
        "min_hull_size": 1,
        "build_cost_xp_delta": 1,
        "order": 2,
    },
    # Quarters
    {
        "key": "crew_quarters",
        "name": "Crew Quarters",
        "description": "Habitable living space for additional crew.",
        "category": "quarters",
        "slot_cost": 1,
        "crew_delta": -5, "energy_delta": 1, "maintenance_delta": 1,
        "min_hull_size": 2,
        "build_cost_xp_delta": 1,
        "order": 1,
    },
    # Cargo
    {
        "key": "cargo_hold",
        "name": "Cargo Hold",
        "description": "Pressurised general-purpose hold.",
        "category": "cargo",
        "slot_cost": 1,
        "crew_delta": 0, "energy_delta": 0, "maintenance_delta": 1,
        "min_hull_size": 1,
        "build_cost_xp_delta": 1,
        "order": 1,
    },
    {
        "key": "fuel_tank",
        "name": "Fuel Tank",
        "description": "Extra propellant and FTL fuel reserves.",
        "category": "cargo",
        "slot_cost": 1,
        "crew_delta": 0, "energy_delta": 0, "maintenance_delta": 1,
        "min_hull_size": 1,
        "build_cost_xp_delta": 1,
        "order": 2,
    },
    # Weapons
    {
        "key": "point_defense",
        "name": "Point Defense Turret",
        "description": "Short-range anti-missile gun; handles drones and incoming fire.",
        "category": "weapons",
        "slot_cost": 1,
        "crew_delta": 1, "energy_delta": 1, "maintenance_delta": 1,
        "min_hull_size": 2,
        "build_cost_xp_delta": 2,
        "order": 1,
    },
    {
        "key": "main_gun",
        "name": "Main Gun",
        "description": "Heavy railgun or particle cannon; the primary offensive weapon.",
        "category": "weapons",
        "slot_cost": 3,
        "crew_delta": 5, "energy_delta": 4, "maintenance_delta": 3,
        "min_hull_size": 4,
        "build_cost_xp_delta": 6,
        "order": 2,
    },
    {
        "key": "missile_bay",
        "name": "Missile Bay",
        "description": "Vertical-launch missile cells for standoff fire.",
        "category": "weapons",
        "slot_cost": 2,
        "crew_delta": 3, "energy_delta": 2, "maintenance_delta": 2,
        "min_hull_size": 3,
        "build_cost_xp_delta": 4,
        "order": 3,
    },
    # Defense
    {
        "key": "armour_plating",
        "name": "Composite Armour",
        "description": "Layered ablative plating. Passive protection.",
        "category": "defense",
        "slot_cost": 1,
        "crew_delta": 0, "energy_delta": 0, "maintenance_delta": 2,
        "min_hull_size": 2,
        "build_cost_xp_delta": 2,
        "order": 1,
    },
    {
        "key": "shield_generator",
        "name": "Shield Generator",
        "description": "Active deflector field; absorbs incoming energy fire.",
        "category": "defense",
        "slot_cost": 2,
        "crew_delta": 2, "energy_delta": 4, "maintenance_delta": 2,
        "min_hull_size": 4,
        "build_cost_xp_delta": 6,
        "order": 2,
    },
    # Sensors
    {
        "key": "sensor_array",
        "name": "Sensor Array",
        "description": "Long-range passive and active sensors.",
        "category": "sensors",
        "slot_cost": 1,
        "crew_delta": 1, "energy_delta": 1, "maintenance_delta": 1,
        "min_hull_size": 1,
        "build_cost_xp_delta": 2,
        "order": 1,
    },
    {
        "key": "ecm_suite",
        "name": "ECM Suite",
        "description": "Electronic countermeasures and stealth baffling.",
        "category": "sensors",
        "slot_cost": 1,
        "crew_delta": 1, "energy_delta": 2, "maintenance_delta": 1,
        "min_hull_size": 2,
        "build_cost_xp_delta": 3,
        "order": 2,
    },
    # Command
    {
        "key": "bridge",
        "name": "Command Bridge",
        "description": "Primary command and control centre.",
        "category": "command",
        "slot_cost": 1,
        "crew_delta": 4, "energy_delta": 1, "maintenance_delta": 1,
        "min_hull_size": 2,
        "build_cost_xp_delta": 2,
        "order": 1,
    },
    {
        "key": "flag_bridge",
        "name": "Flag Bridge",
        "description": "Fleet-level command facility for flagship duty.",
        "category": "command",
        "slot_cost": 2,
        "crew_delta": 8, "energy_delta": 2, "maintenance_delta": 2,
        "min_hull_size": 6,
        "build_cost_xp_delta": 5,
        "order": 2,
    },
    # Hangar (carrier-scoped)
    {
        "key": "drone_bay",
        "name": "Drone Bay",
        "description": "Launch and recovery deck for mining or combat drones.",
        "category": "hangar",
        "slot_cost": 3,
        "crew_delta": 6, "energy_delta": 3, "maintenance_delta": 3,
        "min_hull_size": 5,
        "restricted_to_types": ["carrier", "support"],
        "build_cost_xp_delta": 5,
        "order": 1,
    },
    {
        "key": "fighter_bay",
        "name": "Fighter Bay",
        "description": "Hangar, launch rails, and maintenance deck for solo fighters.",
        "category": "hangar",
        "slot_cost": 4,
        "crew_delta": 10, "energy_delta": 4, "maintenance_delta": 4,
        "min_hull_size": 6,
        "restricted_to_types": ["carrier"],
        "build_cost_xp_delta": 8,
        "order": 2,
    },
]


def seed(apps, schema_editor):
    ShipType = apps.get_model("starships", "ShipType")
    ShipModule = apps.get_model("starships", "ShipModule")
    for row in SHIP_TYPES:
        ShipType.objects.update_or_create(
            key=row["key"],
            defaults={k: v for k, v in row.items() if k != "key"},
        )
    for row in SHIP_MODULES:
        # Ensure restricted_to_types is always present (default empty list).
        defaults = {k: v for k, v in row.items() if k != "key"}
        defaults.setdefault("restricted_to_types", [])
        ShipModule.objects.update_or_create(
            key=row["key"],
            defaults=defaults,
        )


def unseed(apps, schema_editor):
    ShipType = apps.get_model("starships", "ShipType")
    ShipModule = apps.get_model("starships", "ShipModule")
    ShipType.objects.filter(key__in=[r["key"] for r in SHIP_TYPES]).delete()
    ShipModule.objects.filter(key__in=[r["key"] for r in SHIP_MODULES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("starships", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
