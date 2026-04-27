from django.db import migrations, models


COVER_SEED = [
    {"name": "Wooden chair / door", "tier": "light",
     "durability": "1", "health": "4",
     "notes": "Splinters within 2 turns of sustained fire."},
    {"name": "Drywall partition", "tier": "light",
     "durability": "1", "health": "3",
     "notes": "Bullets pass through cleanly at heavy calibre."},
    {"name": "Vehicle door", "tier": "light",
     "durability": "2", "health": "5",
     "notes": "Light cover. Engine block separately = heavy cover."},
    {"name": "Vehicle engine block", "tier": "heavy",
     "durability": "3", "health": "8",
     "notes": "Heavy cover front-on. Other angles = light cover."},
    {"name": "Sandbag stack", "tier": "heavy",
     "durability": "3", "health": "6",
     "notes": "Field-expedient. Stops most small-arms fire."},
    {"name": "Brick wall", "tier": "heavy",
     "durability": "4", "health": "8",
     "notes": "Crumbles under sustained .50-cal."},
    {"name": "Concrete wall", "tier": "full",
     "durability": "5", "health": "10",
     "notes": "Demolition-grade ordnance to breach."},
    {"name": "Reinforced bulkhead", "tier": "full",
     "durability": "7", "health": "15",
     "notes": "Ship-grade armor. AT weapons required."},
]


def seed_cover(apps, schema_editor):
    SiteSettings = apps.get_model("exodus", "SiteSettings")
    obj = SiteSettings.objects.filter(pk=1).first()
    if obj and not obj.cover:
        obj.cover = COVER_SEED
        obj.save(update_fields=["cover"])


def reverse_seed(apps, schema_editor):
    SiteSettings = apps.get_model("exodus", "SiteSettings")
    obj = SiteSettings.objects.filter(pk=1).first()
    if obj:
        obj.cover = []
        obj.save(update_fields=["cover"])


class Migration(migrations.Migration):

    dependencies = [
        ("exodus", "0019_sitesettings_armor"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="cover",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    "List of cover entries. See SiteSettings.default_cover() "
                    "for the seed catalogue and field reference."
                ),
            ),
        ),
        migrations.RunPython(seed_cover, reverse_seed),
    ]
