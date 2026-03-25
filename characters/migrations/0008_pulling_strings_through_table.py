"""Convert pulling_strings from simple M2M to M2M with through table."""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def migrate_m2m_data(apps, schema_editor):
    """Copy existing M2M entries to the new through table."""
    Character = apps.get_model("characters", "Character")
    CharacterPullingString = apps.get_model("characters", "CharacterPullingString")
    # The old M2M table is characters_character_pulling_strings
    db_alias = schema_editor.connection.alias
    for char in Character.objects.using(db_alias).all():
        for ps in char.pulling_strings.using(db_alias).all():
            CharacterPullingString.objects.using(db_alias).create(
                character=char,
                pulling_string=ps,
            )


def reverse_m2m_data(apps, schema_editor):
    """Copy through table entries back to simple M2M."""
    CharacterPullingString = apps.get_model("characters", "CharacterPullingString")
    Character = apps.get_model("characters", "Character")
    db_alias = schema_editor.connection.alias
    for cps in CharacterPullingString.objects.using(db_alias).all():
        cps.character.pulling_strings.add(cps.pulling_string)


class Migration(migrations.Migration):

    dependencies = [
        ("characters", "0007_remove_character_pulling_strings_and_more"),
        ("exodus", "0006_pullingstring_is_linkable"),
        ("npcs", "0005_npc_character_class_npc_class_classified"),
    ]

    operations = [
        # 1. Create the through table
        migrations.CreateModel(
            name="CharacterPullingString",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "character",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="character_pulling_strings",
                        to="characters.character",
                    ),
                ),
                (
                    "pulling_string",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="exodus.pullingstring",
                    ),
                ),
                (
                    "linked_npc",
                    models.ForeignKey(
                        blank=True,
                        help_text="Linked NPC dossier (for linkable pulling strings like Personal NPC).",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="npcs.npc",
                    ),
                ),
            ],
            options={
                "ordering": ["pulling_string__category", "pulling_string__name"],
            },
        ),
        # 2. Migrate existing M2M data to through table
        migrations.RunPython(migrate_m2m_data, reverse_m2m_data),
        # 3. Remove old M2M field
        migrations.RemoveField(
            model_name="character",
            name="pulling_strings",
        ),
        # 4. Add new M2M field with through table
        migrations.AddField(
            model_name="character",
            name="pulling_strings",
            field=models.ManyToManyField(
                blank=True,
                through="characters.CharacterPullingString",
                to="exodus.pullingstring",
            ),
        ),
    ]
