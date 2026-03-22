from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('exodus', '0002_alter_sitesettings_next_game_date'),
    ]

    operations = [
        migrations.AddField(
            model_name='sitesettings',
            name='charter_text',
            field=models.TextField(blank=True, default='', help_text='United Interstellar Council charter content (Markdown).'),
        ),
    ]
