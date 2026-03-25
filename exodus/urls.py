"""URL configuration for exodus project."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

from . import views


urlpatterns = [
    path("admin/", admin.site.urls),
    path("settings/", views.site_settings, name="site-settings"),
    path("api/status/", views.api_status, name="api-status"),
    path("api/pulling-strings/", views.api_pulling_strings, name="api-pulling-strings"),
    path("api/pulling-strings/<int:pk>/", views.api_pulling_string_detail, name="api-pulling-string-detail"),
    path("api/merits/", views.api_merits, name="api-merits"),
    path("api/merits/<int:pk>/", views.api_merit_detail, name="api-merit-detail"),
    path("merits/", views.merits_page, name="merits-page"),
    path("pulling-strings/", views.pulling_strings_page, name="pulling-strings-page"),
    path("accounts/", include("accounts.urls")),
    path("", include("comms.urls")),
    path("", include("characters.urls")),
    path("", include("agencies.urls")),
    path("", include("npcs.urls")),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
