"""URL configuration for the personal combat app.

v0.15.5 adds the WoD 2.0 condition + stance + willpower surface on
top of the v0.15.4 attack endpoints:

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
* ``participants/<id>/conditions/set/``   (v0.15.5) — append a condition tag
* ``participants/<id>/conditions/clear/`` (v0.15.5) — drop a condition tag (or family)
* ``participants/<id>/willpower/``        (v0.15.5) — manual WP adjustment
* ``participants/<id>/full-defense/``     (v0.15.5) — own-turn FULL DEFENSE stance
* ``participants/<id>/dodge/``            (v0.15.5) — roll dodge pool (in or out of turn)

REST JSON endpoints land in v0.15.6+.
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

    # v0.15.24 — Player-ready gate (setup only). GM or character owner
    # toggles the ``ready`` tag on a Character participant; the START
    # button refuses to fire while any character is unready (FORCE
    # START checkbox bypasses for the GM).
    path(
        "combat/<int:pk>/participants/<int:participant_id>/ready/",
        views.toggle_ready,
        name="toggle_ready",
    ),

    # v0.15.26 — surprise round support. GM toggles the per-participant
    # Alert exemption (``surprise_immune`` field). The encounter-wide
    # ``is_surprise_round`` flag is written via ``encounter_update``
    # (no separate URL).
    path(
        "combat/<int:pk>/participants/<int:participant_id>/toggle-alert/",
        views.toggle_alert,
        name="toggle_alert",
    ),

    # POST — equip + cover + attack (v0.15.4)
    path(
        "combat/<int:pk>/participants/<int:participant_id>/equip-weapon/",
        views.equip_weapon,
        name="equip_weapon",
    ),
    # v0.15.16 — equip / unequip an off-hand weapon for dual-wielding.
    # Same form shape as equip_weapon (one ``weapon_name`` field) but
    # writes to ``offhand_weapon_name`` / ``offhand_weapon_data`` and
    # uses the parallel ``offhand_ammo:N`` condition tag.
    path(
        "combat/<int:pk>/participants/<int:participant_id>/equip-offhand/",
        views.equip_offhand,
        name="equip_offhand",
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

    # POST — conditions, willpower, defensive stances (v0.15.5)
    path(
        "combat/<int:pk>/participants/<int:participant_id>/conditions/set/",
        views.set_condition,
        name="set_condition",
    ),
    path(
        "combat/<int:pk>/participants/<int:participant_id>/conditions/clear/",
        views.clear_condition,
        name="clear_condition",
    ),
    path(
        "combat/<int:pk>/participants/<int:participant_id>/willpower/",
        views.adjust_willpower,
        name="adjust_willpower",
    ),
    path(
        "combat/<int:pk>/participants/<int:participant_id>/full-defense/",
        views.full_defense,
        name="full_defense",
    ),
    path(
        "combat/<int:pk>/participants/<int:participant_id>/dodge/",
        views.dodge,
        name="dodge",
    ),
    path(
        "combat/<int:pk>/participants/<int:participant_id>/pass-turn/",
        views.pass_turn,
        name="pass_turn",
    ),
    # v0.15.14 — AIM action. Costs the active turn; grants stackable
    # +N dice on the next attack against the aimed target (cap at +3).
    path(
        "combat/<int:pk>/participants/<int:participant_id>/aim/",
        views.aim,
        name="aim",
    ),
    # v0.15.15 — RELOAD action. Resets the equipped firearm's ammo
    # tag to the catalogue magazine size. Costs the turn when called
    # by the active participant; off-turn reloads are free GM
    # bookkeeping. Players have unlimited magazines (no reserve
    # tracking) so the action is always available. The view callable
    # is ``reload_weapon`` to avoid shadowing Python's builtin
    # ``reload`` at module scope; the URL name stays the natural
    # ``reload`` for caller convenience.
    path(
        "combat/<int:pk>/participants/<int:participant_id>/reload/",
        views.reload_weapon,
        name="reload",
    ),
    # v0.15.26 — off-hand reload. Closes the deferred item from
    # v0.15.16. Same cost rules as the main-hand reload.
    path(
        "combat/<int:pk>/participants/<int:participant_id>/reload-offhand/",
        views.reload_offhand,
        name="reload_offhand",
    ),
    # v0.15.26 — GM-only manual HP adjustment (heal / correct damage).
    # Three integer fields (B / L / A) clamped to 0..health_max with
    # the cumulative sum bounded by the same total. Auto-toggles the
    # incapacitated condition based on the new total.
    path(
        "combat/<int:pk>/participants/<int:participant_id>/adjust-hp/",
        views.adjust_hp,
        name="adjust_hp",
    ),

    # ---------------------------------------------------------------
    # v0.15.7 — JSON API for the MCP server
    # ---------------------------------------------------------------
    # All endpoints under ``/api/admin/combat/`` honour the
    # ``Authorization: Bearer <MCP_API_TOKEN>`` middleware in
    # exodus.mcp_auth (or session-cookie superuser auth). Read +
    # create + lifecycle only — attack / dodge / condition / willpower
    # mutations stay in the web UI by design.
    path(
        "api/admin/combat/encounters/",
        views.api_encounters,
        name="api_list",
    ),
    path(
        "api/admin/combat/encounters/<int:pk>/",
        views.api_encounter_detail,
        name="api_detail",
    ),
    path(
        "api/admin/combat/encounters/<int:pk>/lifecycle/",
        views.api_encounter_lifecycle,
        name="api_lifecycle",
    ),
    path(
        "api/admin/combat/encounters/<int:pk>/initiative/",
        views.api_encounter_initiative,
        name="api_initiative",
    ),
    path(
        "api/admin/combat/encounters/<int:pk>/turn/",
        views.api_encounter_turn,
        name="api_turn",
    ),
    path(
        "api/admin/combat/encounters/<int:pk>/participants/",
        views.api_encounter_participants,
        name="api_participants",
    ),
    path(
        "api/admin/combat/encounters/<int:pk>/participants/<int:participant_id>/",
        views.api_encounter_participant_detail,
        name="api_participant_detail",
    ),
]
