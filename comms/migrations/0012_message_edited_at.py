from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("comms", "0011_threadmembership_defense_active_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="message",
            name="edited_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
