"""URL configuration for exodus project."""
from django.conf import settings
from django.contrib import admin
from django.urls import path, include, re_path
from django.views.static import serve

from . import views


urlpatterns = [
    path("admin/", admin.site.urls),
    # starmap routes now in starmap app
    path("settings/", views.site_settings, name="site-settings"),
    path("settings/impersonate/", views.impersonate_user, name="impersonate-user"),
    path("settings/stop-impersonate/", views.stop_impersonation, name="stop-impersonation"),
    path("api/transfer-player-to-agency/", views.api_transfer_player_to_agency, name="api-transfer-player-to-agency"),
    path("api/status/", views.api_status, name="api-status"),
    path("api/pulling-strings/", views.api_pulling_strings, name="api-pulling-strings"),
    path("api/pulling-strings/<int:pk>/", views.api_pulling_string_detail, name="api-pulling-string-detail"),
    path("api/merits/", views.api_merits, name="api-merits"),
    path("api/merits/<int:pk>/", views.api_merit_detail, name="api-merit-detail"),
    path("api/admin/weapons/", views.api_weapons, name="api-admin-weapons"),
    path("api/admin/weapons/<str:name>/", views.api_weapon_detail, name="api-admin-weapon-detail"),
    path("api/admin/armor/", views.api_armor, name="api-admin-armor"),
    path("api/admin/armor/<str:name>/", views.api_armor_detail, name="api-admin-armor-detail"),
    path("api/admin/cover/", views.api_cover, name="api-admin-cover"),
    path("api/admin/cover/<str:name>/", views.api_cover_detail, name="api-admin-cover-detail"),
    path("api/admin/combat-npcs/", views.api_combat_npcs, name="api-admin-combat-npcs"),
    path("api/admin/combat-npcs/<str:name>/", views.api_combat_npc_detail, name="api-admin-combat-npc-detail"),
    path("rules/", views.rules_page, name="rules-page"),
    path("rules/combat/", views.combat_page, name="combat-page"),
    path("rules/bases/", views.base_building_page, name="base-building-page"),
    path("rules/merits/", views.merits_page, name="merits-page"),
    path("rules/pulling-strings/", views.pulling_strings_page, name="pulling-strings-page"),
    # Legacy aliases — keep old URLs working for bookmarks / external links.
    path("merits/", views.merits_page),
    path("pulling-strings/", views.pulling_strings_page),
    path("accounts/", include("accounts.urls")),
    path("", include("news.urls")),
    path("", include("starmap.urls")),
    path("", include("starships.urls")),
    path("", include("spacebattle.urls")),
    path("", include("combat.urls")),
    path("", include("comms.urls")),
    path("", include("characters.urls")),
    path("", include("agencies.urls")),
    path("", include("npcs.urls")),
    path("", include("gm_workspace.urls")),
]

# Serve uploaded media (portraits, news images, comms attachments) from Django
# itself, regardless of DEBUG. The stock ``static()`` helper registers nothing
# when DEBUG is False, which left every /media/ URL a 404 in production (the
# container runs with DJANGO_DEBUG=False). There is no separate file server in
# front of Daphne for uploads, so this route is the only thing that serves them.
def media_serve(request, path):
    """Serve one file from MEDIA_ROOT, reading the setting at request time."""
    return serve(request, path, document_root=settings.MEDIA_ROOT)


urlpatterns += [
    re_path(r"^media/(?P<path>.*)$", media_serve, name="media"),
]
