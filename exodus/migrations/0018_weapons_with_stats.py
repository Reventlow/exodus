from django.db import migrations


# Inlined here so the migration is self-contained even if the model
# default helper is later edited or moved.
WEAPONS_WITH_STATS = [
    {"name": "Knuckle Buster", "category": "melee", "damage": "1B",
     "range": "—", "capacity": "—", "notes": "Concealed under glove. Subdual-friendly."},
    {"name": "Knife", "category": "melee", "damage": "1L",
     "range": "—", "capacity": "—", "notes": "Concealable. Throwable in a pinch."},
    {"name": "Baton", "category": "melee", "damage": "2B",
     "range": "—", "capacity": "—", "notes": "Police standard. Telescopic variants extend +1 reach."},
    {"name": "Taser (Contact)", "category": "melee", "damage": "1B",
     "range": "—", "capacity": "1 charge",
     "notes": "On hit: target rolls Stamina + Resolve or loses next action."},
    {"name": "Chair", "category": "improvised", "damage": "1B",
     "range": "—", "capacity": "—", "notes": "−1 weapon mod. Breaks on 2+ successes."},
    {"name": "Bottle", "category": "improvised", "damage": "0B",
     "range": "—", "capacity": "—",
     "notes": "Breaks on hit → broken neck = 1L improvised follow-up."},
    {"name": "Phone Book", "category": "improvised", "damage": "0B",
     "range": "—", "capacity": "—", "notes": "Subdual-only. Spreads bashing across track without bruising."},
    {"name": "Hammer", "category": "improvised", "damage": "2B",
     "range": "—", "capacity": "—", "notes": "Workshop tool. +1 dmg to construction-grade armour."},
    {"name": "Hand Gun", "category": "firearm", "damage": "2L",
     "range": "20/40/80 m", "capacity": "12+1",
     "notes": "Concealable. 9 mm or .40 standard."},
    {"name": "Large Hand Gun", "category": "firearm", "damage": "3L",
     "range": "25/50/100 m", "capacity": "8+1",
     "notes": "Magnum / .44 / .50 AE. Heavy recoil — −1 to follow-up shots."},
    {"name": "Sub Machine Gun", "category": "firearm", "damage": "2L",
     "range": "20/40/80 m", "capacity": "30",
     "notes": "Burst-fire +1 dice; autofire +2 in close range."},
    {"name": "Assault Rifle", "category": "firearm", "damage": "3L",
     "range": "100/200/400 m", "capacity": "30",
     "notes": "Burst-fire +1; autofire +2/+3."},
    {"name": "DMR", "category": "firearm", "damage": "4L",
     "range": "200/400/800 m", "capacity": "20",
     "notes": "Semi-auto designated marksman rifle. Pairs well with optics."},
    {"name": "Shotgun", "category": "firearm", "damage": "4L close / 2L long",
     "range": "5/10/40 m", "capacity": "5+1",
     "notes": "Pump-action. Damage drops with range as shot spreads."},
    {"name": "Twin-Barrel Shotgun", "category": "firearm", "damage": "5L (both barrels)",
     "range": "5/10/40 m", "capacity": "2",
     "notes": "Fire one or both. Both = +1 damage, then full reload."},
    {"name": "Auto Shotgun", "category": "firearm", "damage": "4L",
     "range": "5/10/40 m", "capacity": "8",
     "notes": "Box-fed. Burst-fire +1 dice at close range."},
    {"name": "Scoped Rifle", "category": "firearm", "damage": "4L",
     "range": "250/500/1000 m", "capacity": "5+1",
     "notes": "−2 initiative; +1 aim per turn (max +3) with proper scope."},
    {"name": "Taser (Cartridge)", "category": "firearm", "damage": "1L + stun",
     "range": "4/8/15 m", "capacity": "1 cartridge",
     "notes": "On hit: Stamina + Resolve or stunned for [successes] turns."},
    {"name": "Throwing Knife", "category": "thrown", "damage": "1L",
     "range": "Str ×3 / ×6 / ×12 m", "capacity": "—",
     "notes": "Recoverable on retrieval. Concealable."},
    {"name": "Throwing Axe", "category": "thrown", "damage": "2L",
     "range": "Str ×3 / ×6 / ×12 m", "capacity": "—",
     "notes": "Heavy — Str 2 minimum. Devastating at close range."},
]


def upgrade_weapons(apps, schema_editor):
    """If existing weapons are name-only legacy entries (from migration
    0017), replace with the new enriched defaults. Custom user-edited
    entries with stats already populated are preserved."""
    SiteSettings = apps.get_model("exodus", "SiteSettings")
    obj = SiteSettings.objects.filter(pk=1).first()
    if not obj:
        return
    existing = obj.weapons or []
    is_legacy = (
        not existing
        or all(
            isinstance(w, dict) and set(w.keys()) <= {"name", "category"}
            for w in existing
        )
    )
    if is_legacy:
        obj.weapons = WEAPONS_WITH_STATS
        obj.save(update_fields=["weapons"])


def downgrade_weapons(apps, schema_editor):
    """Strip the stat fields back to name+category only."""
    SiteSettings = apps.get_model("exodus", "SiteSettings")
    obj = SiteSettings.objects.filter(pk=1).first()
    if not obj or not isinstance(obj.weapons, list):
        return
    obj.weapons = [
        {"name": w.get("name", ""), "category": w.get("category", "")}
        for w in obj.weapons if isinstance(w, dict)
    ]
    obj.save(update_fields=["weapons"])


class Migration(migrations.Migration):

    dependencies = [
        ("exodus", "0017_sitesettings_weapons"),
    ]

    operations = [
        migrations.RunPython(upgrade_weapons, downgrade_weapons),
    ]
