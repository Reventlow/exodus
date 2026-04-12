"""Seed the six canonical ResourceType rows.

Idempotent — uses update_or_create so re-running or re-seeding is safe.
Values are the agreed galaxy-wide ranges and unit labels.
"""

from django.db import migrations


CANONICAL_RESOURCES = [
    {
        "key": "ice",
        "name": "Water Ice",
        "color": "#7dd3fc",
        "icon": "\u2744",
        "order": 1,
        "unit_label": "carrier loads",
        "unit_description": "1 load = one drone-carrier refuel of H2O/H2/O2.",
        "typical_min": 5,
        "typical_max": 80,
        "rarity_weight": 0.90,
        "scan_bracket_wide": 25,
        "scan_bracket_narrow": 8,
    },
    {
        "key": "metals",
        "name": "Metallic Ore",
        "color": "#cbd5e1",
        "icon": "\u26cf",
        "order": 2,
        "unit_label": "kt ore",
        "unit_description": "Kilotons of raw construction-grade metallic ore.",
        "typical_min": 10,
        "typical_max": 500,
        "rarity_weight": 0.85,
        "scan_bracket_wide": 150,
        "scan_bracket_narrow": 40,
    },
    {
        "key": "rareEarth",
        "name": "Rare Earths",
        "color": "#c084fc",
        "icon": "\u269b",
        "order": 3,
        "unit_label": "kt refined",
        "unit_description": "Kilotons of refined rare-earth elements for electronics.",
        "typical_min": 0,
        "typical_max": 20,
        "rarity_weight": 0.40,
        "scan_bracket_wide": 8,
        "scan_bracket_narrow": 2,
    },
    {
        "key": "helium3",
        "name": "Helium-3",
        "color": "#fbbf24",
        "icon": "\u2600",
        "order": 4,
        "unit_label": "canisters",
        "unit_description": "Pressurised canisters of He-3 fusion fuel.",
        "typical_min": 0,
        "typical_max": 15,
        "rarity_weight": 0.35,
        "scan_bracket_wide": 6,
        "scan_bracket_narrow": 2,
    },
    {
        "key": "hydrocarbons",
        "name": "Hydrocarbons",
        "color": "#fb923c",
        "icon": "\U0001F6E2",
        "order": 5,
        "unit_label": "tanks",
        "unit_description": "Storage tanks of liquid hydrocarbons (methane/ethane).",
        "typical_min": 0,
        "typical_max": 120,
        "rarity_weight": 0.55,
        "scan_bracket_wide": 40,
        "scan_bracket_narrow": 12,
    },
    {
        "key": "exotic",
        "name": "Exotic Matter",
        "color": "#f472b6",
        "icon": "\u2728",
        "order": 6,
        "unit_label": "fragments",
        "unit_description": "Stabilised fragments of exotic matter — FTL research fuel.",
        "typical_min": 0,
        "typical_max": 3,
        "rarity_weight": 0.08,
        "scan_bracket_wide": 2,
        "scan_bracket_narrow": 1,
    },
]


def seed_resource_types(apps, schema_editor):
    ResourceType = apps.get_model("starmap", "ResourceType")
    for row in CANONICAL_RESOURCES:
        ResourceType.objects.update_or_create(
            key=row["key"],
            defaults={k: v for k, v in row.items() if k != "key"},
        )


def unseed_resource_types(apps, schema_editor):
    ResourceType = apps.get_model("starmap", "ResourceType")
    ResourceType.objects.filter(
        key__in=[r["key"] for r in CANONICAL_RESOURCES],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("starmap", "0006_resourcetype_units"),
    ]

    operations = [
        migrations.RunPython(seed_resource_types, unseed_resource_types),
    ]
