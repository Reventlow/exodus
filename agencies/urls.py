from django.urls import path
from . import views

urlpatterns = [
    # Pages
    path("agencies/", views.agency_list_page, name="agency_list"),
    path("agencies/<int:pk>/", views.agency_sheet_page, name="agency_sheet"),
    # API
    path("api/agencies/", views.api_agency_list, name="api_agency_list"),
    path("api/agencies/<int:pk>/", views.api_agency_detail, name="api_agency_detail"),
    path(
        "api/agencies/<int:pk>/visibility/",
        views.api_toggle_visibility,
        name="api_toggle_visibility",
    ),
    path(
        "api/agencies/<int:pk>/changes/",
        views.api_change_request_list,
        name="api_change_request_list",
    ),
    path(
        "api/changes/<int:pk>/review/",
        views.api_change_request_review,
        name="api_change_request_review",
    ),
    path(
        "api/agencies/notifications/",
        views.api_notification_count,
        name="api_notification_count",
    ),
]
