"""URL configuration for the news application."""

from django.urls import path

from . import views

app_name = "news"

urlpatterns = [
    # Page views
    path("", views.news_list_page, name="list"),
    path("news/<slug:slug>/", views.news_detail_page, name="detail"),

    # API endpoints
    path("api/news/", views.api_news_list, name="api-list"),
    path("api/news/<int:pk>/", views.api_news_detail, name="api-detail"),
    path("api/news/<int:pk>/release/", views.api_news_release, name="api-release"),
    path("api/news/<int:pk>/share/", views.api_news_share, name="api-share"),
    path("api/news/<int:pk>/image/", views.api_news_image, name="api-image"),
    path("api/news/<int:pk>/attachments/", views.api_news_attachment, name="api-attachment"),
    path(
        "api/news/<int:pk>/attachments/<int:attachment_pk>/",
        views.api_news_attachment_delete,
        name="api-attachment-delete",
    ),
]
