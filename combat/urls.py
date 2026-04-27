"""URL configuration for the personal combat app.

Phase 0 only ships the GM-only placeholder pages. REST endpoints
land in Phase 1.
"""

from django.urls import path

from . import views


app_name = "combat"

urlpatterns = [
    path("combat/", views.encounter_list_page, name="list"),
    path("combat/<int:pk>/", views.encounter_page, name="detail"),
]
