"""Add shield, battery, and weapon-profile fields + seed canonical modules.

Mechanics notes:
- Fighter guns: short range, low damage, strong vs small targets
  (size_bias negative)
- Main guns: medium range, solid damage, better vs large targets
- Titan cannons: long range, huge damage, very high battery cost,
  specifically anti-large
- Anti-small-craft missiles: LONG range only (min_range set), best
  vs small, slow travel
- Torpedoes: long range, slow travel, best vs large
- Shields: temp HP pool + battery capacity + per-activation cost
- Sensors: handled in v0.14.11 via scanning_delta
- Thrusters: speed/defense as before; GM adjudicates the "less
  effective on big hulls" rule for now
- Bridge: parked, not yet finalised
"""

from django.db import migrations, models


SHIP_TYPE_BATTERY = {
    "drone":       2,
    "solo":        3,
    "shuttle":     4,
    "cruiser":     8,
    "support":     8,
    "carrier":    12,
    "dreadnaught":16,
    "titan":      24,
}


# Shield modules: (shield_delta, battery_delta, battery_cost)
SHIELD_MODULES = {
    "shield_generator":  (5, 3, 2),  # standalone
    "shields_l1":        (3, 2, 1),
    "shields_l2":        (5, 3, 2),
    "shields_l3":        (8, 4, 2),
    "shields_l4":       (12, 5, 3),
    "shields_l5":       (18, 6, 4),
}


# Weapon profiles: (damage, range, min_range, size_bias, travel_turns, battery_cost)
WEAPON_MODULES = {
    # Standalone weapons — kept roughly in line with their tiered siblings
    "point_defense":  (1, 2, 0, -3, 0, 0),
    "main_gun":       (4, 6, 0,  2, 0, 1),
    "missile_bay":    (3, 7, 1, -2, 1, 0),

    # Fighter Guns — anti-small, short range
    "fighter_guns_l1": (1, 3, 0, -2, 0, 0),
    "fighter_guns_l2": (2, 3, 0, -2, 0, 0),
    "fighter_guns_l3": (2, 4, 0, -2, 0, 0),
    "fighter_guns_l4": (3, 4, 0, -3, 0, 0),
    "fighter_guns_l5": (4, 5, 0, -3, 0, 1),

    # Main Guns — anti-large, medium range
    "main_guns_l1": (3,  5, 0, 2, 0, 1),
    "main_guns_l2": (4,  6, 0, 2, 0, 1),
    "main_guns_l3": (5,  7, 0, 3, 0, 2),
    "main_guns_l4": (6,  8, 0, 3, 0, 2),
    "main_guns_l5": (8, 10, 0, 4, 0, 3),

    # Titan Cannons — capital spinal guns, huge damage, huge battery
    "titan_cannon_l1": ( 6, 10, 0, 5, 0, 3),
    "titan_cannon_l2": ( 8, 12, 0, 5, 0, 4),
    "titan_cannon_l3": (10, 12, 0, 6, 0, 5),
    "titan_cannon_l4": (14, 14, 0, 6, 0, 6),
    "titan_cannon_l5": (20, 16, 0, 8, 0, 8),

    # Anti-Small-Craft Missiles — long range ONLY (min_range enforced),
    # slow travel, strong vs small, useless at close range
    "anti_small_missiles_l1": (2,  6, 2, -3, 1, 0),
    "anti_small_missiles_l2": (2,  7, 2, -3, 1, 0),
    "anti_small_missiles_l3": (3,  8, 3, -4, 2, 1),
    "anti_small_missiles_l4": (4,  9, 3, -4, 2, 1),
    "anti_small_missiles_l5": (5, 10, 3, -5, 2, 2),

    # Torpedoes — long range, slow travel, strong vs large
    "torpedoes_l1": ( 5,  8, 3, 3, 1, 1),
    "torpedoes_l2": ( 6,  9, 3, 3, 1, 1),
    "torpedoes_l3": ( 8, 10, 4, 4, 2, 2),
    "torpedoes_l4": (10, 11, 4, 4, 2, 2),
    "torpedoes_l5": (15, 12, 5, 5, 3, 3),
}


def seed(apps, schema_editor):
    ShipType = apps.get_model("starships", "ShipType")
    ShipModule = apps.get_model("starships", "ShipModule")

    for key, battery in SHIP_TYPE_BATTERY.items():
        ShipType.objects.filter(key=key).update(base_battery_power=battery)

    for key, (shield, bat_delta, bat_cost) in SHIELD_MODULES.items():
        ShipModule.objects.filter(key=key).update(
            shield_delta=shield,
            battery_delta=bat_delta,
            battery_cost=bat_cost,
        )

    for key, (dmg, rng, minr, bias, travel, bat) in WEAPON_MODULES.items():
        ShipModule.objects.filter(key=key).update(
            weapon_damage=dmg,
            weapon_range=rng,
            weapon_min_range=minr,
            weapon_size_bias=bias,
            weapon_travel_turns=travel,
            battery_cost=bat,
        )


def unseed(apps, schema_editor):
    ShipType = apps.get_model("starships", "ShipType")
    ShipModule = apps.get_model("starships", "ShipModule")
    ShipType.objects.filter(key__in=SHIP_TYPE_BATTERY.keys()).update(base_battery_power=3)
    ShipModule.objects.filter(
        key__in=list(SHIELD_MODULES.keys()) + list(WEAPON_MODULES.keys())
    ).update(
        shield_delta=0, battery_delta=0, battery_cost=0,
        weapon_damage=0, weapon_range=0, weapon_min_range=0,
        weapon_size_bias=0, weapon_travel_turns=0,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("starships", "0008_scanning_stat"),
    ]

    operations = [
        # ShipType — shield + battery baselines
        migrations.AddField(
            model_name="shiptype",
            name="base_shield",
            field=models.IntegerField(default=0, help_text="Temporary hit-point pool (shield generators add to this)."),
        ),
        migrations.AddField(
            model_name="shiptype",
            name="base_battery_power",
            field=models.IntegerField(default=3, help_text="Battery capacity — shields and heavy weapons drain it during combat."),
        ),
        # ShipModule — shield/battery + weapon profile
        migrations.AddField(
            model_name="shipmodule",
            name="shield_delta",
            field=models.IntegerField(default=0, help_text="Added to the shield temp-HP pool."),
        ),
        migrations.AddField(
            model_name="shipmodule",
            name="battery_delta",
            field=models.IntegerField(default=0, help_text="Added to battery capacity."),
        ),
        migrations.AddField(
            model_name="shipmodule",
            name="battery_cost",
            field=models.IntegerField(default=0, help_text="Per-activation battery draw during combat."),
        ),
        migrations.AddField(
            model_name="shipmodule",
            name="weapon_damage",
            field=models.IntegerField(default=0, help_text="Base hit damage (before defense/armor)."),
        ),
        migrations.AddField(
            model_name="shipmodule",
            name="weapon_range",
            field=models.IntegerField(default=0, help_text="Maximum hex range (0 = not a weapon / no range)."),
        ),
        migrations.AddField(
            model_name="shipmodule",
            name="weapon_min_range",
            field=models.IntegerField(default=0, help_text="Minimum hex range — anti-air missiles etc. can't fire closer."),
        ),
        migrations.AddField(
            model_name="shipmodule",
            name="weapon_size_bias",
            field=models.IntegerField(
                default=0,
                help_text=(
                    "Target-size bias. Positive = better vs LARGER targets "
                    "(main guns, torpedoes). Negative = better vs SMALLER "
                    "targets (fighter guns, AA missiles)."
                ),
            ),
        ),
        migrations.AddField(
            model_name="shipmodule",
            name="weapon_travel_turns",
            field=models.IntegerField(default=0, help_text="Projectile travel time in rounds. 0 = hitscan."),
        ),
        migrations.RunPython(seed, unseed),
    ]
