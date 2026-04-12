from django.contrib import admin

from .models import NewsArticle, NewsAttachment


class NewsAttachmentInline(admin.TabularInline):
    model = NewsAttachment
    extra = 1


@admin.register(NewsArticle)
class NewsArticleAdmin(admin.ModelAdmin):
    list_display = ["title", "visibility", "eyes_only_player", "published_at", "created_at"]
    list_filter = ["visibility"]
    search_fields = ["title", "content"]
    prepopulated_fields = {"slug": ("title",)}
    inlines = [NewsAttachmentInline]


@admin.register(NewsAttachment)
class NewsAttachmentAdmin(admin.ModelAdmin):
    list_display = ["filename", "article", "uploaded_at"]
