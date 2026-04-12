"""URL configuration for the starmap application."""

from django.urls import path

from . import views

app_name = "starmap"

urlpatterns = [
    # Page
    path("starmap/", views.starmap_page, name="page"),

    # Star systems API
    path("api/starmap/systems/", views.api_star_systems, name="api-systems"),
    path("api/starmap/systems/<int:pk>/", views.api_star_system_detail, name="api-system-detail"),
    path("api/starmap/admin/import/", views.api_admin_import, name="api-admin-import"),
    path("api/starmap/admin/seed/", views.api_seed_systems, name="api-admin-seed"),

    # Agency scans
    path("api/agencies/<int:pk>/scans/", views.api_agency_scan_list, name="api-scan-list"),
    path("api/agencies/<int:pk>/scans/<int:scan_id>/", views.api_agency_scan_detail, name="api-scan-detail"),
    path("api/agencies/<int:pk>/scans/<int:scan_id>/roll/", views.api_scan_roll, name="api-scan-roll"),
    path("api/agencies/<int:pk>/scans/<int:scan_id>/roll-log/", views.api_scan_roll_log, name="api-scan-roll-log"),
    path("api/agencies/<int:pk>/scans/<int:scan_id>/meta/", views.api_scan_meta, name="api-scan-meta"),
    path("api/agencies/<int:pk>/scans/<int:scan_id>/share/", views.api_share_scan, name="api-share-scan"),

    # Claims
    path("api/starmap/systems/<int:pk>/claim/", views.api_claim_system, name="api-claim"),

    # Resource types
    path("api/starmap/resource-types/", views.api_resource_types, name="api-resource-types"),
    path("api/starmap/resource-types/<int:pk>/", views.api_resource_type_detail, name="api-resource-type-detail"),

    # Civilisations
    path("api/starmap/civilisations/", views.api_civilisations, name="api-civilisations"),
    path("api/starmap/civilisations/<int:pk>/", views.api_civilisation_detail, name="api-civilisation-detail"),

    # Star system civilisations
    path("api/starmap/systems/<int:pk>/civilisations/", views.api_system_civilisations, name="api-system-civs"),
    path("api/starmap/systems/<int:pk>/civilisations/<int:civ_pk>/", views.api_system_civilisation_detail, name="api-system-civ-detail"),

    # Star system planets
    path("api/starmap/systems/<int:pk>/planets/", views.api_system_planets, name="api-system-planets"),
    path("api/starmap/systems/<int:pk>/planets/<int:planet_pk>/", views.api_system_planet_detail, name="api-system-planet-detail"),

    # City maps
    path("citymap/<int:pk>/", views.citymap_page, name="citymap"),
    path("api/citymaps/", views.api_citymap_list, name="api-citymap-list"),
    path("api/citymaps/<int:pk>/", views.api_citymap_detail, name="api-citymap-detail"),
    path("api/citymaps/<int:pk>/markers/", views.api_citymap_marker_create, name="api-citymap-marker-create"),
    path("api/citymaps/<int:pk>/markers/<int:marker_pk>/", views.api_citymap_marker_detail, name="api-citymap-marker-detail"),
]
