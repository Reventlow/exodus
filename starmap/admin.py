from django.contrib import admin

from .models import StarSystem, AgencyScan, ScanRollLog, CityMap, CityMapMarker, ResourceType, Civilisation, StarSystemCivilisation, Planet


class StarSystemCivilisationInline(admin.TabularInline):
    model = StarSystemCivilisation
    extra = 0


class PlanetInline(admin.TabularInline):
    model = Planet
    extra = 0


@admin.register(StarSystem)
class StarSystemAdmin(admin.ModelAdmin):
    list_display = ["name", "distance", "spectral_type", "discovered", "has_livable_planet", "difficulty_mod", "claimed_by"]
    list_editable = ["discovered", "has_livable_planet", "difficulty_mod"]
    list_filter = ["discovered", "has_livable_planet", "spectral_type", "is_sol", "is_endgame"]
    search_fields = ["name"]
    inlines = [StarSystemCivilisationInline, PlanetInline]


@admin.register(AgencyScan)
class AgencyScanAdmin(admin.ModelAdmin):
    list_display = ["agency", "star_system", "scan_level", "player", "base_name"]
    list_filter = ["scan_level"]


@admin.register(ScanRollLog)
class ScanRollLogAdmin(admin.ModelAdmin):
    list_display = ["character_name", "star_system_name", "successes", "rolled_at"]


@admin.register(ResourceType)
class ResourceTypeAdmin(admin.ModelAdmin):
    list_display = ["key", "name", "color", "order"]
    ordering = ["order"]


@admin.register(Civilisation)
class CivilisationAdmin(admin.ModelAdmin):
    list_display = ["name", "tech_level", "disposition", "is_hidden"]
    list_filter = ["tech_level", "disposition", "is_hidden"]


@admin.register(StarSystemCivilisation)
class StarSystemCivilisationAdmin(admin.ModelAdmin):
    list_display = ["star_system", "civilisation", "discovered", "scan_level_required"]


@admin.register(Planet)
class PlanetAdmin(admin.ModelAdmin):
    list_display = ["name", "star_system", "planet_type", "atmosphere", "life_type", "habitable", "discovered"]
    list_filter = ["planet_type", "atmosphere", "life_type", "habitable", "discovered"]


class CityMapMarkerInline(admin.TabularInline):
    model = CityMapMarker
    extra = 0


@admin.register(CityMap)
class CityMapAdmin(admin.ModelAdmin):
    list_display = ["name", "latitude", "longitude", "enabled", "visible_to_players"]
    inlines = [CityMapMarkerInline]


@admin.register(CityMapMarker)
class CityMapMarkerAdmin(admin.ModelAdmin):
    list_display = ["label", "city_map", "marker_type", "visible_to_players"]
