"""URL configuration for the spacebattle application."""

from django.urls import path

from . import views

app_name = "spacebattle"

urlpatterns = [
    # Pages
    path("spacebattle/", views.battles_list_page, name="list"),
    path("spacebattle/<int:pk>/", views.battle_page, name="detail"),

    # Battles
    path("api/spacebattle/battles/", views.api_battles, name="api-battles"),
    path(
        "api/spacebattle/battles/<int:pk>/",
        views.api_battle_detail,
        name="api-battle-detail",
    ),
    path(
        "api/spacebattle/battles/<int:pk>/start/",
        views.api_battle_start,
        name="api-battle-start",
    ),
    path(
        "api/spacebattle/battles/<int:pk>/next-turn/",
        views.api_battle_next_turn,
        name="api-battle-next-turn",
    ),
    path(
        "api/spacebattle/battles/<int:pk>/end/",
        views.api_battle_end,
        name="api-battle-end",
    ),
    path(
        "api/spacebattle/battles/<int:pk>/log/",
        views.api_battle_log,
        name="api-battle-log",
    ),
    path(
        "api/spacebattle/battles/<int:pk>/simulate/",
        views.api_battle_simulate,
        name="api-battle-simulate",
    ),

    # Participants
    path(
        "api/spacebattle/battles/<int:battle_pk>/participants/",
        views.api_participants,
        name="api-participants",
    ),
    path(
        "api/spacebattle/battles/<int:battle_pk>/participants/<int:pk>/",
        views.api_participant_detail,
        name="api-participant-detail",
    ),
    path(
        "api/spacebattle/battles/<int:battle_pk>/participants/<int:pk>/move/",
        views.api_participant_move,
        name="api-participant-move",
    ),
    path(
        "api/spacebattle/battles/<int:battle_pk>/participants/<int:pk>/fire/",
        views.api_participant_fire,
        name="api-participant-fire",
    ),
    path(
        "api/spacebattle/battles/<int:battle_pk>/participants/<int:pk>/apply-damage/",
        views.api_participant_apply_damage,
        name="api-participant-apply-damage",
    ),
]
