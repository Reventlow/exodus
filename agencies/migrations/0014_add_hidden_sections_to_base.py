from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agencies', '0013_add_is_hidden_to_base'),
    ]

    operations = [
        migrations.AddField(
            model_name='base',
            name='hidden_sections',
            field=models.JSONField(default=list, help_text='List of section keys hidden from non-superusers (e.g. facilities, equipment).'),
        ),
    ]
