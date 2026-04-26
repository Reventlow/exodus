from django.urls import path
from . import views

urlpatterns = [
    # Pages
    path("agencies/", views.agency_list_page, name="agency_list"),
    path("agencies/map/", views.world_map_page, name="world_map"),
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
        "api/agencies/<int:pk>/ftl/<int:assignment_id>/meta/",
        views.api_ftl_meta,
        name="api_ftl_meta",
    ),
    path(
        "api/agencies/<int:pk>/ftl/<int:assignment_id>/fringe-effect/",
        views.api_ftl_fringe_effect,
        name="api_ftl_fringe_effect",
    ),
    path(
        "api/agencies/<int:pk>/ftl/<int:assignment_id>/roll/",
        views.api_ftl_roll,
        name="api_ftl_roll",
    ),
    path(
        "api/agencies/<int:pk>/ftl/<int:assignment_id>/roll-log/",
        views.api_ftl_roll_log,
        name="api_ftl_roll_log",
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
    path("api/council/reorder/", views.api_council_reorder, name="api_council_reorder"),
    path("api/council/members/", views.api_council_members, name="api_council_members"),
    path(
        "api/council/chairman/<int:pk>/",
        views.api_council_set_chairman,
        name="api_council_set_chairman",
    ),
    path(
        "api/council/presence/<int:pk>/",
        views.api_council_toggle_presence,
        name="api_council_toggle_presence",
    ),
    path(
        "api/council/<int:pk>/",
        views.api_council_detail,
        name="api_council_detail",
    ),
    path(
        "api/council/<int:pk>/vote/",
        views.api_council_vote,
        name="api_council_vote",
    ),
    # Pages — base config
    path("agencies/base-config/", views.base_config_page, name="base_config"),
    # API — world map
    path("api/map-data/", views.api_map_data, name="api_map_data"),
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
    # Per-base section PATCH (Phase 1/2 — multi-player concurrency).
    # section_key ∈ {name, location, merits, facilities, workspaces,
    # equipment, departments, notes, geo, hidden, classified}.
    path(
        "api/agencies/<int:pk>/bases/<int:base_id>/section/<str:section_key>/",
        views.api_agency_base_section,
        name="api_agency_base_section",
    ),
    # Agency-level section PATCH (Phase 1/2 — multi-player concurrency).
    # See views.py for permission per section.
    path(
        "api/agencies/<int:pk>/section/header/",
        views.api_agency_section_header,
        name="api_agency_section_header",
    ),
    path(
        "api/agencies/<int:pk>/section/alliance/",
        views.api_agency_section_alliance,
        name="api_agency_section_alliance",
    ),
    path(
        "api/agencies/<int:pk>/section/notes/",
        views.api_agency_section_notes,
        name="api_agency_section_notes",
    ),
    path(
        "api/agencies/<int:pk>/section/integrity/",
        views.api_agency_section_integrity,
        name="api_agency_section_integrity",
    ),
    path(
        "api/agencies/<int:pk>/section/attributes/",
        views.api_agency_section_attributes,
        name="api_agency_section_attributes",
    ),
    path(
        "api/agencies/<int:pk>/section/specializations/",
        views.api_agency_section_specializations,
        name="api_agency_section_specializations",
    ),
    path(
        "api/agencies/<int:pk>/section/merits/",
        views.api_agency_section_merits,
        name="api_agency_section_merits",
    ),
    path(
        "api/agencies/<int:pk>/section/flaws/",
        views.api_agency_section_flaws,
        name="api_agency_section_flaws",
    ),
    path(
        "api/agencies/<int:pk>/section/assets/",
        views.api_agency_section_assets,
        name="api_agency_section_assets",
    ),
    path(
        "api/agencies/<int:pk>/section/fleet/",
        views.api_agency_section_fleet,
        name="api_agency_section_fleet",
    ),
    path(
        "api/agencies/<int:pk>/section/history/",
        views.api_agency_section_history,
        name="api_agency_section_history",
    ),
    path(
        "api/agencies/<int:pk>/section/admin-flags/",
        views.api_agency_section_admin_flags,
        name="api_agency_section_admin_flags",
    ),
    # Dark Grants
    path(
        "api/agencies/<int:pk>/projects/<int:project_index>/dark-grants/",
        views.api_dark_grants,
        name="api_dark_grants",
    ),
    path(
        "api/agencies/<int:pk>/projects/<int:project_index>/stimulants/",
        views.api_stimulants,
        name="api_stimulants",
    ),
    path(
        "api/agencies/<int:pk>/projects/<int:project_index>/stimulants/unlock/",
        views.api_stimulants_unlock,
        name="api_stimulants_unlock",
    ),
    path(
        "api/agencies/<int:pk>/projects/<int:project_index>/live-testing/",
        views.api_live_testing,
        name="api_live_testing",
    ),
    path(
        "api/agencies/<int:pk>/projects/<int:project_index>/fringe-effect/",
        views.api_fringe_effect,
        name="api_fringe_effect",
    ),
    # Downtime actions
    path(
        "api/agencies/<int:pk>/downtime/",
        views.api_downtime_action,
        name="api_downtime_action",
    ),
    # Project rolls
    path(
        "api/agencies/<int:pk>/projects/<int:project_index>/roll/",
        views.api_project_roll,
        name="api_project_roll",
    ),
    path(
        "api/agencies/<int:pk>/projects/<int:project_index>/roll-log/",
        views.api_project_roll_log,
        name="api_project_roll_log",
    ),
    # Complete project
    path(
        "api/agencies/<int:pk>/projects/<int:project_index>/complete/",
        views.api_complete_project,
        name="api_complete_project",
    ),
    # Stat change logs
    path(
        "api/agencies/<int:pk>/stat-logs/",
        views.api_stat_logs,
        name="api_stat_logs",
    ),
    # Conditions
    path(
        "api/agencies/<int:pk>/conditions/<int:condition_id>/sweep/",
        views.api_sweep_condition,
        name="api_sweep_condition",
    ),
    path(
        "api/agencies/<int:pk>/conditions/<int:condition_id>/",
        views.api_condition_detail,
        name="api_condition_detail",
    ),
]
