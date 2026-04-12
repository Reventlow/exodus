"""Admin registration for the starships app.

Basic ModelAdmin entries so GMs can poke at starship data from Django
admin while the in-app UI is still under construction (Releases B–F).
"""

from django.contrib import admin

from .models import (
    ClassModule,
    Fleet,
    ShipModule,
    ShipType,
    Starship,
    StarshipClass,
)


@admin.register(ShipType)
class ShipTypeAdmin(admin.ModelAdmin):
    list_display = [
        "name", "key", "default_slot_budget",
        "min_size", "max_size", "base_crew", "order",
    ]
    ordering = ["order", "name"]
    search_fields = ["name", "key"]


@admin.register(ShipModule)
class ShipModuleAdmin(admin.ModelAdmin):
    list_display = [
        "name", "category", "slot_cost",
        "crew_delta", "energy_delta", "maintenance_delta",
        "provides_sublight", "provides_ftl", "min_hull_size",
    ]
    list_filter = ["category", "provides_sublight", "provides_ftl"]
    search_fields = ["name", "key"]
    ordering = ["category", "order", "name"]


class ClassModuleInline(admin.TabularInline):
    model = ClassModule
    extra = 0


@admin.register(StarshipClass)
class StarshipClassAdmin(admin.ModelAdmin):
    list_display = [
        "name", "ship_type", "size", "created_by",
        "is_locked", "build_cost_xp", "build_required_successes",
    ]
    list_filter = ["ship_type", "is_locked"]
    search_fields = ["name"]
    inlines = [ClassModuleInline]


@admin.register(Fleet)
class FleetAdmin(admin.ModelAdmin):
    list_display = ["name", "agency", "commander"]
    list_filter = ["agency"]
    search_fields = ["name", "commander"]


@admin.register(Starship)
class StarshipAdmin(admin.ModelAdmin):
    list_display = [
        "name", "hull_number", "starship_class", "agency",
        "fleet", "status", "current_crew", "maintenance_state",
    ]
    list_filter = ["status", "agency", "starship_class__ship_type"]
    search_fields = ["name", "hull_number"]
