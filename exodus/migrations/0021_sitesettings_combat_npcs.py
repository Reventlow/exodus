from django.db import migrations, models


# Inlined seed catalogue for the combat NPC templates. Kept in-migration
# (mirroring 0018/0019/0020) so this file remains self-contained even if
# ``SiteSettings.default_combat_npcs()`` is later edited.
COMBAT_NPCS_SEED = [
    # Guard — civilian / building security
    {"name": "Generic Guard", "category": "guard", "combat_pool": "4", "defense": "2",
     "health_max": "7", "armor_rating": "—", "weapon": "Baton",
     "notes": "Untrained civilian-grade security. Calls for backup early."},
    {"name": "Building Security", "category": "guard", "combat_pool": "5", "defense": "3",
     "health_max": "7", "armor_rating": "1/2", "weapon": "Hand Gun",
     "notes": "Trained corporate security. Wears soft armor under uniform."},
    {"name": "Bouncer", "category": "guard", "combat_pool": "6", "defense": "2",
     "health_max": "8", "armor_rating": "—", "weapon": "Knuckle Buster",
     "notes": "Big, brutish, brawler. Subdues rather than kills."},
    # Razor — street fighters / mercenaries
    {"name": "Street Razor", "category": "razor", "combat_pool": "5", "defense": "3",
     "health_max": "7", "armor_rating": "—", "weapon": "Knife",
     "notes": "Cyberware addict, jittery, unpredictable. Will close to melee."},
    {"name": "Cyber-Razor", "category": "razor", "combat_pool": "7", "defense": "4",
     "health_max": "7", "armor_rating": "1/2", "weapon": "Large Hand Gun",
     "notes": "Augmented street operator. Reflex-boost wetware."},
    {"name": "Pit Fighter", "category": "razor", "combat_pool": "7", "defense": "4",
     "health_max": "8", "armor_rating": "—", "weapon": "Knuckle Buster",
     "notes": "Underground brawl champion. Pain Tolerance 2 (ignore wound penalty −1)."},
    # Corp — corporate security ladders
    {"name": "Corp Sec Officer", "category": "corp", "combat_pool": "6", "defense": "3",
     "health_max": "7", "armor_rating": "2/2", "weapon": "Sub Machine Gun",
     "notes": "Mid-tier corporate security. Trained, equipped, expendable."},
    {"name": "Executive Bodyguard", "category": "corp", "combat_pool": "7", "defense": "4",
     "health_max": "7", "armor_rating": "3/3", "weapon": "Hand Gun",
     "notes": "Personal protection detail. Will throw self in front of principal."},
    {"name": "Black Ops Operator", "category": "corp", "combat_pool": "9", "defense": "5",
     "health_max": "8", "armor_rating": "4/4", "weapon": "Assault Rifle",
     "notes": "Special-forces grade. Suppressed weapons, night-vision optics, IR."},
    # Cultist — zealous followers
    {"name": "Cultist Initiate", "category": "cultist", "combat_pool": "4", "defense": "2",
     "health_max": "7", "armor_rating": "—", "weapon": "Knife",
     "notes": "Fanatical, no fear of death. Charges into melee shouting prayers."},
    {"name": "Cultist Adept", "category": "cultist", "combat_pool": "6", "defense": "3",
     "health_max": "7", "armor_rating": "—", "weapon": "Hand Gun",
     "notes": "Combat-trained believer. Coordinates with other cultists."},
    {"name": "Cultist Champion", "category": "cultist", "combat_pool": "8", "defense": "4",
     "health_max": "8", "armor_rating": "3/3", "weapon": "Assault Rifle",
     "notes": "Inner-circle warrior. Carries a relic; +1 to ally morale rolls."},
    # Drone — autonomous / non-human
    {"name": "Sentry Drone", "category": "drone", "combat_pool": "5", "defense": "4",
     "health_max": "5", "armor_rating": "2/2", "weapon": "Sub Machine Gun",
     "notes": "Hovering or wheeled. Cannot be intimidated. Targets nearest threat."},
    {"name": "Combat Drone", "category": "drone", "combat_pool": "7", "defense": "4",
     "health_max": "7", "armor_rating": "3/3", "weapon": "Assault Rifle",
     "notes": "Military-grade. Targets via thermal imaging — concealment less effective."},
    {"name": "Guard Dog", "category": "drone", "combat_pool": "5", "defense": "3",
     "health_max": "6", "armor_rating": "—", "weapon": "Bite (1L + grapple)",
     "notes": "Trained attack animal. Grapples on hit; victim Strength + Brawl to break."},
]


def seed_combat_npcs(apps, schema_editor):
    SiteSettings = apps.get_model("exodus", "SiteSettings")
    obj = SiteSettings.objects.filter(pk=1).first()
    if obj and not obj.combat_npcs:
        obj.combat_npcs = COMBAT_NPCS_SEED
        obj.save(update_fields=["combat_npcs"])


def reverse_seed(apps, schema_editor):
    SiteSettings = apps.get_model("exodus", "SiteSettings")
    obj = SiteSettings.objects.filter(pk=1).first()
    if obj:
        obj.combat_npcs = []
        obj.save(update_fields=["combat_npcs"])


class Migration(migrations.Migration):

    dependencies = [
        ("exodus", "0020_sitesettings_cover"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="combat_npcs",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    "List of combat NPC stat-block entries. See "
                    "SiteSettings.default_combat_npcs() for the seed "
                    "catalogue and field reference."
                ),
            ),
        ),
        migrations.RunPython(seed_combat_npcs, reverse_seed),
    ]
