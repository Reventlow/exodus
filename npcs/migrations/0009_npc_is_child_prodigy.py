from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('npcs', '0008_add_compromised_state'),
    ]

    operations = [
        migrations.AddField(
            model_name='npc',
            name='is_child_prodigy',
            field=models.BooleanField(default=False, help_text='Tagged as a child prodigy recruited via fringe science.'),
        ),
    ]
