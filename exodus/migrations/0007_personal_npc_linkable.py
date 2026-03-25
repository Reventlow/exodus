"""Set Personal NPC as linkable with XP cost."""

from django.db import migrations


def set_personal_npc(apps, schema_editor):
    PullingString = apps.get_model("exodus", "PullingString")
    PullingString.objects.filter(name="Personal NPC").update(
        is_linkable=True, cost=2,
    )


def unset_personal_npc(apps, schema_editor):
    PullingString = apps.get_model("exodus", "PullingString")
    PullingString.objects.filter(name="Personal NPC").update(
        is_linkable=False, cost=0,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("exodus", "0006_pullingstring_is_linkable"),
    ]

    operations = [
        migrations.RunPython(set_personal_npc, unset_personal_npc),
    ]
