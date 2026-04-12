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
]
