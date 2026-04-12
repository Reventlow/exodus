from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agencies', '0025_agency_project_rolls'),
    ]

    operations = [
        migrations.AddField(
            model_name='agencyftlproject',
            name='player',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
        migrations.AddField(
            model_name='agencyftlproject',
            name='base_id',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='agencyftlproject',
            name='base_name',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
        migrations.AddField(
            model_name='agencyftlproject',
            name='metadata',
            field=models.JSONField(default=dict, help_text='Project metadata: dicePoolConfig, fringe, fringe effects, assignedNpcs, completionEffects, etc.'),
        ),
    ]
