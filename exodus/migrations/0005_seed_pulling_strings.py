"""Seed initial pulling strings catalog."""

from django.db import migrations


PULLING_STRINGS = [
    # General
    ("Staff", "A general staff of 8 people to help you with everyday tasks. They follow you around.", 3, "general"),
    ("Personal NPC", "Links to a Dossier the character has assigned to them.", 0, "general"),
    ("Smuggle through Emergency Aid", "You know who to pay to smuggle through emergency aid shipments.", 4, "general"),
    ("NGO Pull", "You have the ability to affect relief and aid efforts and even start and stop them.", 3, "general"),
    ("Alternate Identities", "You have a lot of alternative identities with the perfect paperwork and cover stories and even registered in government databases. Sometimes you ask yourself do you know who you are.", 5, "general"),
    # Fixer
    ("Social Media Manipulation", "You have access to the best social media companies that can influence social media towards or against agendas/people... and more.", 4, "fixer"),
    ("Institute Sanctions", "You are able to get governments you represent to institute governmental sanctions immediately towards countries.", 4, "fixer"),
    ("Secretary Access", "Secretaries have their own gossip lines. And you have a good connection with them to get info on what is on the down low...", 2, "fixer"),
    ("Activist Groups", "You have a good connection with most of the activist groups. They may not all like you but they will take your call and meet you if needed.", 3, "fixer"),
    # Soldier
    ("Green Men", "Activate separatist movements, rebels or crime organisations. Perfect if instability or Casus Belli is needed.", 3, "soldier"),
    ("Gain Access to Military Gear & Prototypes", "Sometimes something is created off the books, or prototypes go missing from loyal bases or manufacturers.", 4, "soldier"),
    ("Paramilitary & Mercenary Forces", "You are able to hire paramilitary and/or mercenary forces to do off the books ops.", 3, "soldier"),
]


def seed_pulling_strings(apps, schema_editor):
    PullingString = apps.get_model("exodus", "PullingString")
    for name, description, cost, category in PULLING_STRINGS:
        PullingString.objects.get_or_create(
            name=name,
            defaults={
                "description": description,
                "cost": cost,
                "category": category,
            },
        )


def unseed_pulling_strings(apps, schema_editor):
    PullingString = apps.get_model("exodus", "PullingString")
    names = [ps[0] for ps in PULLING_STRINGS]
    PullingString.objects.filter(name__in=names).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("exodus", "0004_pullingstring"),
    ]

    operations = [
        migrations.RunPython(seed_pulling_strings, unseed_pulling_strings),
    ]
