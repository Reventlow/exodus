"""URL configuration for exodus project."""
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect


urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("", include("comms.urls")),
    path("", include("characters.urls")),
    path("", include("agencies.urls")),
]
