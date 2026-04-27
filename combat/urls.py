"""URL configuration for the personal combat app.

v0.15.3 extends the v0.15.2 CRUD surface with the initiative + turn
advance endpoints:

* ``initiative/<participant>/`` — single-participant roll
* ``initiative/all/``           — roll-all for unrolled participants
* ``initiative/clear/``         — wipe rolls + reset to setup
* ``start/``                    — setup → active, round 1
* ``next-turn/``                — advance pointer or roll round
* ``end/``                      — active → concluded

REST JSON endpoints land in v0.15.4+.
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
]
