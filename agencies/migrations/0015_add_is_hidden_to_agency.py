from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agencies', '0014_add_hidden_sections_to_base'),
    ]

    operations = [
        migrations.AddField(
            model_name='agency',
            name='is_hidden',
            field=models.BooleanField(default=False, help_text='Hidden agencies are only visible to superusers.'),
        ),
    ]
