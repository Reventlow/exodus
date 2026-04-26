from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_add_userprofile"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="last_activity",
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                help_text=(
                    "Most recent authenticated HTTP request from this user. "
                    "Updated by LastActivityMiddleware, debounced to once per 30s "
                    "to limit DB writes. Used for activity monitoring; not exposed "
                    "to other players."
                ),
                null=True,
            ),
        ),
    ]
