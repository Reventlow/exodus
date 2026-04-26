"""URL configuration for the GM workspace."""
from django.urls import path

from . import views

app_name = "gm_workspace"

urlpatterns = [
    # GM-only — story ideas
    path("gm/", views.workspace_landing, name="landing"),
    path("gm/story-ideas/", views.story_ideas_page, name="ideas-page"),
    path("api/gm/story-ideas/", views.api_story_ideas_list, name="api-list"),
    path("api/gm/story-ideas/<int:pk>/", views.api_story_ideas_detail, name="api-detail"),

    # GM-only — timeline
    path("gm/timeline/", views.timeline_page, name="timeline-page"),
    path("api/gm/timeline/", views.api_timeline_list, name="api-timeline-list"),
    path("api/gm/timeline/<int:pk>/", views.api_timeline_detail, name="api-timeline-detail"),

    # GM-only — campaign log
    path("gm/campaign-log/", views.campaign_log_page, name="campaign-log-page"),
    path("api/gm/campaign-log/", views.api_campaign_sessions_list, name="api-sessions-list"),
    path("api/gm/campaign-log/<int:pk>/", views.api_campaign_sessions_detail, name="api-sessions-detail"),

    # Player-facing briefs
    path("my-briefs/", views.briefs_page, name="briefs-page"),
    path("api/my-briefs/", views.api_briefs_list, name="api-briefs-list"),
    path("api/my-briefs/<int:pk>/", views.api_briefs_detail, name="api-briefs-detail"),
]
