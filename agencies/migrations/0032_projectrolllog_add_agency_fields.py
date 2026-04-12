"""Add agency, project_index, project_name to ProjectRollLog and make assignment nullable."""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("agencies", "0031_projectrolllog"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectrolllog",
            name="agency",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="project_roll_logs",
                to="agencies.agency",
                null=True,  # Allow null temporarily for existing rows
            ),
        ),
        migrations.AddField(
            model_name="projectrolllog",
            name="project_index",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="projectrolllog",
            name="project_name",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
        migrations.AlterField(
            model_name="projectrolllog",
            name="assignment",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="roll_logs",
                to="agencies.agencyftlproject",
            ),
        ),
    ]
