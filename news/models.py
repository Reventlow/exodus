"""Models for the news application."""

import os

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class NewsArticle(models.Model):
    """A news article with visibility controls for the RPG landing page."""

    VISIBILITY_CHOICES = [
        ("hidden", "Hidden"),       # Only superusers
        ("eyes_only", "Eyes Only"), # Superuser + designated player
        ("public", "Public"),       # All authenticated users
    ]

    title = models.CharField(max_length=300)
    slug = models.SlugField(max_length=300, unique=True, blank=True)
    content = models.TextField(help_text="Article body in Markdown format")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="news_articles",
    )
    visibility = models.CharField(
        max_length=20,
        choices=VISIBILITY_CHOICES,
        default="hidden",
    )
    eyes_only_player = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eyes_only_news",
        help_text="Player who can see this eyes-only article and release it",
    )
    shared_with = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="shared_news",
        help_text="Additional players who can see this eyes-only article",
    )
    released_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the eyes-only article was released to all players",
    )
    game_date = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="In-game date displayed on the article (e.g. '9 February 2036, Evening')",
    )
    game_date_sort = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Sortable in-game datetime for ordering articles chronologically",
    )
    featured_image = models.ImageField(
        upload_to="news/images/",
        blank=True,
        null=True,
    )
    featured_image_full = models.BooleanField(
        default=False,
        help_text="Show full image instead of cropping to fit",
    )
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-game_date_sort", "-created_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title) or "article"
            slug = base_slug
            counter = 1
            while NewsArticle.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        if self.visibility == "public" and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    def is_visible_to(self, user):
        """Check if a user can see this article."""
        if user.is_superuser:
            return True
        if self.visibility == "public":
            return True
        if self.visibility == "eyes_only":
            if self.eyes_only_player == user:
                return True
            if self.shared_with.filter(pk=user.pk).exists():
                return True
        return False

    def can_release(self, user):
        """Check if a user can release this article to public."""
        if self.visibility != "eyes_only":
            return False
        return user == self.eyes_only_player or user.is_superuser


class NewsAttachment(models.Model):
    """File attachment on a news article."""

    article = models.ForeignKey(
        NewsArticle,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    file = models.FileField(upload_to="news/attachments/")
    filename = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at"]

    def __str__(self):
        return self.filename

    def save(self, *args, **kwargs):
        if not self.filename and self.file:
            self.filename = os.path.basename(self.file.name)
        super().save(*args, **kwargs)
