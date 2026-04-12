"""URL configuration for the starships application."""

from django.urls import path

from . import views

app_name = "starships"

urlpatterns = [
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
]
