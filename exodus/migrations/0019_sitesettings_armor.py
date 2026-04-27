from django.db import migrations, models


ARMOR_SEED = [
    {"name": "Reinforced Coat", "category": "light", "rating": "1/0",
     "str_min": "—", "penalty": "—",
     "notes": "Concealable. Slash-resistant lining; bullets pass."},
    {"name": "Kevlar Vest", "category": "light", "rating": "1/2",
     "str_min": "—", "penalty": "—",
     "notes": "Soft armor. Concealable under street clothes."},
    {"name": "Tactical Vest", "category": "light", "rating": "2/2",
     "str_min": "—", "penalty": "−1 Def",
     "notes": "Visible. MOLLE attachments. Civilian-legal."},
    {"name": "Riot Gear", "category": "medium", "rating": "2/3",
     "str_min": "1", "penalty": "−1 Def, −1 Spd",
     "notes": "Helmet + chest + limb plates. Police standard."},
    {"name": "Plate Carrier", "category": "medium", "rating": "3/3",
     "str_min": "2", "penalty": "−1 Def, −1 Spd",
     "notes": "Ceramic / steel inserts. Visible. Combat-grade."},
    {"name": "EOD Suit", "category": "medium", "rating": "4/4",
     "str_min": "2", "penalty": "−2 Def, −2 Spd",
     "notes": "Bomb disposal. Helmet + groin plate. Limited mobility."},
    {"name": "Full Ballistic", "category": "heavy", "rating": "4/4",
     "str_min": "2", "penalty": "−2 Def, −1 Spd",
     "notes": "Full body coverage. Modern military issue."},
    {"name": "Combat Plate", "category": "heavy", "rating": "5/5",
     "str_min": "3", "penalty": "−2 Def, −2 Spd",
     "notes": "Hardened ceramic + composite. Visible armor signature."},
    {"name": "Powered Exo-Frame", "category": "heavy", "rating": "5/5",
     "str_min": "—", "penalty": "−1 Def",
     "notes": "Powered assist (+2 effective Str). 8h charge. Loud."},
    {"name": "EVA Suit", "category": "vacuum", "rating": "1/1",
     "str_min": "—", "penalty": "−1 Def",
     "notes": "Sealed pressure suit. 6h life support. Industrial standard."},
    {"name": "Hardsuit", "category": "vacuum", "rating": "3/3",
     "str_min": "2", "penalty": "−2 Def, −1 Spd",
     "notes": "Sealed combat suit. 12h life support. Helmet HUD."},
    {"name": "Industrial Hardsuit", "category": "vacuum", "rating": "4/4",
     "str_min": "2", "penalty": "−2 Def, −2 Spd",
     "notes": "Sealed. Powered manipulators (+2 Str for lifting). 24h life support."},
]


def seed_armor(apps, schema_editor):
    SiteSettings = apps.get_model("exodus", "SiteSettings")
    obj = SiteSettings.objects.filter(pk=1).first()
    if obj and not obj.armor:
        obj.armor = ARMOR_SEED
        obj.save(update_fields=["armor"])


def reverse_seed(apps, schema_editor):
    SiteSettings = apps.get_model("exodus", "SiteSettings")
    obj = SiteSettings.objects.filter(pk=1).first()
    if obj:
        obj.armor = []
        obj.save(update_fields=["armor"])


class Migration(migrations.Migration):

    dependencies = [
        ("exodus", "0018_weapons_with_stats"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="armor",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    "List of armor entries. See SiteSettings.default_armor() "
                    "for the seed catalogue and field reference."
                ),
            ),
        ),
        migrations.RunPython(seed_armor, reverse_seed),
    ]
