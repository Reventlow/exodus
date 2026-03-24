from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agencies', '0012_council_presence'),
    ]

    operations = [
        migrations.AddField(
            model_name='base',
            name='is_hidden',
            field=models.BooleanField(default=False, help_text='Hidden bases are only visible to superusers.'),
        ),
        migrations.AddField(
            model_name='base',
            name='hidden_sections',
            field=models.JSONField(default=list, help_text='List of section keys hidden from non-superusers (e.g. facilities, equipment).'),
        ),
    ]
