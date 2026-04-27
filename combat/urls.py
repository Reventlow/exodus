"""URL configuration for the personal combat app.

v0.15.2 ships the GM-only encounter list / detail pages plus the
five POST CRUD endpoints (encounter create / update / delete +
participant add / remove). REST JSON endpoints land in v0.15.3+.
"""

from django.urls import path

from . import views


app_name = "combat"

urlpatterns = [
    # GET — directory + per-encounter detail page
    path("combat/", views.encounter_list_page, name="list"),
    path("combat/<int:pk>/", views.encounter_page, name="detail"),

    # POST — encounter CRUD
    path("combat/create/", views.encounter_create, name="create"),
    path("combat/<int:pk>/update/", views.encounter_update, name="update"),
    path("combat/<int:pk>/delete/", views.encounter_delete, name="delete"),

    # POST — participant CRUD
    path(
        "combat/<int:pk>/participants/add/",
        views.participant_add,
        name="participant_add",
    ),
    path(
        "combat/<int:pk>/participants/<int:participant_id>/remove/",
        views.participant_remove,
        name="participant_remove",
    ),
]
