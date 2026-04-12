from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agencies', '0024_agencystatlog'),
    ]

    operations = [
        migrations.AddField(
            model_name='agency',
            name='project_rolls',
            field=models.JSONField(default=dict, help_text='Roll allocations: {"_global": {"free": N, "spare": N}, "CharName": {"free": N, "spare": N}}'),
        ),
    ]
