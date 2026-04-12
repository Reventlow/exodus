"""URL configuration for the starships application."""

from django.urls import path

from . import views

app_name = "starships"

urlpatterns = [
    # Page
    path("starships/", views.starships_page, name="page"),

    # Release B — catalogue CRUD
    path("api/starships/ship-types/", views.api_ship_types, name="api-ship-types"),
    path(
        "api/starships/ship-types/<int:pk>/",
        views.api_ship_type_detail,
        name="api-ship-type-detail",
    ),
    path("api/starships/modules/", views.api_ship_modules, name="api-modules"),
    path(
        "api/starships/modules/<int:pk>/",
        views.api_ship_module_detail,
        name="api-module-detail",
    ),
    path(
        "api/starships/module-sections/",
        views.api_ship_module_sections,
        name="api-module-sections",
    ),
    path(
        "api/starships/module-sections/<int:pk>/",
        views.api_ship_module_section_detail,
        name="api-module-section-detail",
    ),

    # Release C — classes + class modules
    path("api/starships/classes/", views.api_classes, name="api-classes"),
    path(
        "api/starships/classes/<int:pk>/",
        views.api_class_detail,
        name="api-class-detail",
    ),
    path(
        "api/starships/classes/<int:pk>/modules/",
        views.api_class_add_module,
        name="api-class-add-module",
    ),
    path(
        "api/starships/classes/<int:pk>/modules/<int:cm_id>/",
        views.api_class_module_detail,
        name="api-class-module-detail",
    ),

    # Release D — ship instances + construction progress
    path("api/starships/ships/", views.api_ships, name="api-ships"),
    path(
        "api/starships/ships/<int:pk>/",
        views.api_ship_detail,
        name="api-ship-detail",
    ),
    path(
        "api/starships/ships/<int:pk>/construction-roll/",
        views.api_ship_construction_roll,
        name="api-ship-construction-roll",
    ),

    # Release E — fleets
    path("api/starships/fleets/", views.api_fleets, name="api-fleets"),
    path(
        "api/starships/fleets/<int:pk>/",
        views.api_fleet_detail,
        name="api-fleet-detail",
    ),

    # Release F — legacy fleet import
    path("api/starships/legacy-status/", views.api_legacy_status, name="api-legacy-status"),
    path("api/starships/import-legacy/", views.api_legacy_import, name="api-legacy-import"),
]
