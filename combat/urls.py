"""URL configuration for the personal combat app.

v0.15.4 layers attack actions and equipment management on top of the
v0.15.3 initiative + turn advance surface:

* ``initiative/<participant>/``                — single-participant roll
* ``initiative/all/``                          — roll-all for unrolled participants
* ``initiative/clear/``                        — wipe rolls + reset to setup
* ``start/``                                   — setup → active, round 1
* ``next-turn/``                               — advance pointer or roll round
* ``end/``                                     — active → concluded
* ``participants/<id>/equip-weapon/``  (v0.15.4) — snapshot weapon catalogue entry
* ``participants/<id>/equip-armor/``   (v0.15.4) — snapshot armor catalogue entry
* ``participants/<id>/cover/``         (v0.15.4) — set cover state + entry
* ``participants/<attacker>/attack/``  (v0.15.4) — resolve attack vs target_id

REST JSON endpoints land in v0.15.5+.
"""

from django.urls import path

from . import views


app_name = "combat"

urlpatterns = [
    # GET — directory + per-encounter detail page
    path("combat/", views.encounter_list_page, name="list"),
    path("combat/<int:pk>/", views.encounter_page, name="detail"),

    # POST — encounter CRUD
    path("combat/create/", views.encounter_create, name="create"),
    path("combat/<int:pk>/update/", views.encounter_update, name="update"),
    path("combat/<int:pk>/delete/", views.encounter_delete, name="delete"),

    # POST — participant CRUD
    path(
        "combat/<int:pk>/participants/add/",
        views.participant_add,
        name="participant_add",
    ),
    path(
        "combat/<int:pk>/participants/<int:participant_id>/remove/",
        views.participant_remove,
        name="participant_remove",
    ),

    # POST — initiative + turn advance (v0.15.3)
    # Literal subpaths (all / clear) come first so they win over the
    # int-converter pattern. (``<int:participant_id>`` only matches
    # digits so the ordering is technically safe either way, but
    # explicit is better than implicit.)
    path(
        "combat/<int:pk>/initiative/all/",
        views.roll_initiative_all,
        name="roll_initiative_all",
    ),
    path(
        "combat/<int:pk>/initiative/clear/",
        views.clear_initiative,
        name="clear_initiative",
    ),
    path(
        "combat/<int:pk>/initiative/<int:participant_id>/",
        views.roll_initiative,
        name="roll_initiative",
    ),
    path("combat/<int:pk>/start/", views.start_encounter, name="start"),
    path("combat/<int:pk>/next-turn/", views.next_turn, name="next_turn"),
    path("combat/<int:pk>/end/", views.end_encounter, name="end"),

    # POST — equip + cover + attack (v0.15.4)
    path(
        "combat/<int:pk>/participants/<int:participant_id>/equip-weapon/",
        views.equip_weapon,
        name="equip_weapon",
    ),
    path(
        "combat/<int:pk>/participants/<int:participant_id>/equip-armor/",
        views.equip_armor,
        name="equip_armor",
    ),
    path(
        "combat/<int:pk>/participants/<int:participant_id>/cover/",
        views.set_cover,
        name="set_cover",
    ),
    path(
        "combat/<int:pk>/participants/<int:attacker_id>/attack/",
        views.attack,
        name="attack",
    ),
]
