from django.contrib import admin
from .models import Character


@admin.register(Character)
class CharacterAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "concept", "updated_at")
    list_filter = ("owner",)
    search_fields = ("name", "concept", "owner__username")
