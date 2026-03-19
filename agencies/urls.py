from django.urls import path
from . import views

urlpatterns = [
    # Pages
    path("agencies/", views.agency_list_page, name="agency_list"),
    path("agencies/global-flaws/", views.global_flaws_page, name="global_flaws"),
    path("agencies/ftl-projects/", views.ftl_projects_page, name="ftl_projects"),
    path("agencies/council/", views.council_page, name="council"),
    path("agencies/council/charter/", views.council_charter_page, name="council_charter"),
    path("agencies/<int:pk>/", views.agency_sheet_page, name="agency_sheet"),
    # API — global flaws
    path("api/global-flaws/", views.api_global_flaw_list, name="api_global_flaw_list"),
    path(
        "api/global-flaws/<int:pk>/",
        views.api_global_flaw_detail,
        name="api_global_flaw_detail",
    ),
    # API — FTL projects (global CRUD)
    path(
        "api/ftl-projects/",
        views.api_ftl_project_list,
        name="api_ftl_project_list",
    ),
    path(
        "api/ftl-projects/<int:pk>/",
        views.api_ftl_project_detail,
        name="api_ftl_project_detail",
    ),
    # API — agencies
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
    # API — agency FTL assignments
    path(
        "api/agencies/<int:pk>/ftl/",
        views.api_agency_ftl_assign,
        name="api_agency_ftl_assign",
    ),
    path(
        "api/agencies/<int:pk>/ftl/<int:assignment_id>/",
        views.api_agency_ftl_detail,
        name="api_agency_ftl_detail",
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
    # API — council items & membership
    path("api/council/", views.api_council_list, name="api_council_list"),
    path("api/council/members/", views.api_council_members, name="api_council_members"),
    path(
        "api/council/chairman/<int:pk>/",
        views.api_council_set_chairman,
        name="api_council_set_chairman",
    ),
    path(
        "api/council/<int:pk>/",
        views.api_council_detail,
        name="api_council_detail",
    ),
    # Pages — base config
    path("agencies/base-config/", views.base_config_page, name="base_config"),
    # API — base config (singleton)
    path("api/base-config/", views.api_base_config, name="api_base_config"),
    # API — agency bases
    path(
        "api/agencies/<int:pk>/bases/",
        views.api_agency_base_list,
        name="api_agency_base_list",
    ),
    path(
        "api/agencies/<int:pk>/bases/<int:base_id>/",
        views.api_agency_base_detail,
        name="api_agency_base_detail",
    ),
]
