"""Add combat stats to ShipType and ShipModule.

Smaller hulls get speed/defense/init, bigger hulls get health/armor.
Modules can push any of the four stats via deltas so armour plating
and shield generators actually mean something in the battle sim.
"""

from django.db import migrations, models


SHIP_TYPE_STATS = {
    # key:             (health, speed, defense, armor)
    "drone":           (3,   6, 5, 0),
    "solo":            (5,   5, 4, 1),
    "shuttle":         (8,   4, 3, 1),
    "cruiser":         (25,  3, 2, 3),
    "support":         (20,  3, 2, 2),
    "carrier":         (40,  2, 1, 4),
    "dreadnaught":     (60,  2, 1, 6),
    "titan":           (100, 1, 0, 8),
}


# Modules that actually produce combat deltas. Everything else stays
# at zero and can be tuned from Settings later.
MODULE_DELTAS = {
    # Standalone modules
    "armour_plating":    {"armor_delta": 2, "speed_delta": -1},
    "shield_generator":  {"defense_delta": 2, "health_delta": 5},
    "sublight_drive":    {"speed_delta": 1},
    "ftl_drive":         {},  # no combat delta

    # Shields tier family
    "shields_l1":  {"defense_delta": 1, "health_delta": 3},
    "shields_l2":  {"defense_delta": 2, "health_delta": 5},
    "shields_l3":  {"defense_delta": 2, "health_delta": 8},
    "shields_l4":  {"defense_delta": 3, "health_delta": 12},
    "shields_l5":  {"defense_delta": 4, "health_delta": 18},

    # Armour tier family
    "armour_l1": {"armor_delta": 1},
    "armour_l2": {"armor_delta": 2},
    "armour_l3": {"armor_delta": 3, "speed_delta": -1},
    "armour_l4": {"armor_delta": 4, "speed_delta": -1},
    "armour_l5": {"armor_delta": 6, "speed_delta": -2},

    # Manoeuvring thrusters tier family
    "manoeuvring_thrusters_l1": {"speed_delta": 1, "defense_delta": 1},
    "manoeuvring_thrusters_l2": {"speed_delta": 1, "defense_delta": 1},
    "manoeuvring_thrusters_l3": {"speed_delta": 2, "defense_delta": 2},
    "manoeuvring_thrusters_l4": {"speed_delta": 2, "defense_delta": 2},
    "manoeuvring_thrusters_l5": {"speed_delta": 3, "defense_delta": 3},

    # Sublight engines tier family — these replace the core drive
    "sublight_engines_l1": {"speed_delta": 1},
    "sublight_engines_l2": {"speed_delta": 2},
    "sublight_engines_l3": {"speed_delta": 3},
    "sublight_engines_l4": {"speed_delta": 4},
    "sublight_engines_l5": {"speed_delta": 5},

    # Big weapons that tax speed
    "main_gun":      {"speed_delta": -1},
    "main_guns_l4":  {"speed_delta": -1},
    "main_guns_l5":  {"speed_delta": -2},
    "titan_cannon_l3": {"speed_delta": -1},
    "titan_cannon_l4": {"speed_delta": -1},
    "titan_cannon_l5": {"speed_delta": -2},
}


def seed_stats(apps, schema_editor):
    ShipType = apps.get_model("starships", "ShipType")
    ShipModule = apps.get_model("starships", "ShipModule")

    for key, (health, speed, defense, armor) in SHIP_TYPE_STATS.items():
        ShipType.objects.filter(key=key).update(
            base_health=health,
            base_speed=speed,
            base_defense=defense,
            base_armor=armor,
        )

    for key, deltas in MODULE_DELTAS.items():
        ShipModule.objects.filter(key=key).update(**deltas)


def unseed_stats(apps, schema_editor):
    ShipType = apps.get_model("starships", "ShipType")
    ShipModule = apps.get_model("starships", "ShipModule")
    ShipType.objects.filter(key__in=SHIP_TYPE_STATS.keys()).update(
        base_health=5, base_speed=3, base_defense=0, base_armor=0,
    )
    ShipModule.objects.filter(key__in=MODULE_DELTAS.keys()).update(
        health_delta=0, speed_delta=0, defense_delta=0, armor_delta=0,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("starships", "0006_shiptype_initiative_bonus"),
    ]

    operations = [
        # ShipType combat baselines
        migrations.AddField(
            model_name="shiptype",
            name="base_health",
            field=models.IntegerField(default=5, help_text="Hit-point pool before module deltas."),
        ),
        migrations.AddField(
            model_name="shiptype",
            name="base_speed",
            field=models.IntegerField(default=3, help_text="Hexes of movement per turn (before thrusters)."),
        ),
        migrations.AddField(
            model_name="shiptype",
            name="base_defense",
            field=models.IntegerField(default=0, help_text="Evasion rating — subtracted from an attacker's successes."),
        ),
        migrations.AddField(
            model_name="shiptype",
            name="base_armor",
            field=models.IntegerField(default=0, help_text="Damage reduction — subtracted from damage after defense."),
        ),
        # ShipModule combat deltas
        migrations.AddField(
            model_name="shipmodule",
            name="health_delta",
            field=models.IntegerField(default=0, help_text="Added to hit-point pool."),
        ),
        migrations.AddField(
            model_name="shipmodule",
            name="speed_delta",
            field=models.IntegerField(default=0, help_text="Added to movement range per turn."),
        ),
        migrations.AddField(
            model_name="shipmodule",
            name="defense_delta",
            field=models.IntegerField(default=0, help_text="Added to evasion rating."),
        ),
        migrations.AddField(
            model_name="shipmodule",
            name="armor_delta",
            field=models.IntegerField(default=0, help_text="Added to damage reduction."),
        ),
        migrations.RunPython(seed_stats, unseed_stats),
    ]
