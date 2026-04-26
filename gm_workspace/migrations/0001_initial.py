from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="StoryIdea",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=300)),
                ("content", models.TextField(blank=True, default="", help_text="Markdown")),
                ("tags", models.CharField(blank=True, default="", help_text="Comma-separated free-text tags.", max_length=500)),
                ("pinned", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True, null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="created_story_ideas",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "shared_with",
                    models.ManyToManyField(
                        blank=True,
                        related_name="shared_story_ideas",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-pinned", "-updated_at"],
            },
        ),
    ]
