import characters.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('npcs', '0003_add_is_hidden_to_npc'),
    ]

    operations = [
        migrations.AddField(
            model_name='npc',
            name='attributes',
            field=models.JSONField(default=characters.models.default_attributes),
        ),
        migrations.AddField(
            model_name='npc',
            name='skills',
            field=models.JSONField(default=characters.models.default_skills),
        ),
        migrations.AddField(
            model_name='npc',
            name='health_bashing',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='npc',
            name='health_lethal',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='npc',
            name='health_aggravated',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='npc',
            name='size',
            field=models.IntegerField(default=5),
        ),
        migrations.AddField(
            model_name='npc',
            name='mental_load',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='npc',
            name='willpower_current',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='npc',
            name='experience',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='npc',
            name='merits',
            field=models.JSONField(default=list),
        ),
        migrations.AddField(
            model_name='npc',
            name='flaws',
            field=models.JSONField(default=list),
        ),
        migrations.AddField(
            model_name='npc',
            name='specialisations',
            field=models.JSONField(default=list),
        ),
    ]
