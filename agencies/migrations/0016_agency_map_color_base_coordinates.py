from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agencies', '0015_add_is_hidden_to_agency'),
    ]

    operations = [
        migrations.AddField(
            model_name='agency',
            name='map_color',
            field=models.CharField(blank=True, default='', help_text='Hex color for the world map (e.g. #ff0000).', max_length=7),
        ),
        migrations.AddField(
            model_name='base',
            name='latitude',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='base',
            name='longitude',
            field=models.FloatField(blank=True, null=True),
        ),
    ]
