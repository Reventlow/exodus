"""URL configuration for the comms application."""

from django.urls import path

from . import cyber_views, views

app_name = "comms"

urlpatterns = [
    # Page view
    path("comms/", views.comms_index, name="index"),

    # API endpoints
    path("api/comms/threads/", views.thread_list, name="thread-list"),
    path("api/comms/threads/<int:thread_id>/", views.thread_detail, name="thread-detail"),
    path("api/comms/threads/<int:thread_id>/delete/", views.delete_thread, name="delete-thread"),
    path("api/comms/threads/<int:thread_id>/alias/", views.update_alias, name="update-alias"),
    path("api/comms/threads/<int:thread_id>/messages/", views.send_message, name="send-message"),
    path("api/comms/threads/<int:thread_id>/members/", views.add_member, name="add-member"),
    path(
        "api/comms/threads/<int:thread_id>/members/<int:user_id>/",
        views.remove_member,
        name="remove-member",
    ),
    path("api/comms/threads/<int:thread_id>/join/", views.admin_join, name="admin-join"),
    path("api/comms/threads/<int:thread_id>/read/", views.mark_read, name="mark-read"),
    path("api/comms/unread/", views.unread_count, name="unread-count"),
    path("api/comms/users/", views.user_list, name="user-list"),
    path("api/comms/dossiers/", views.dossier_list, name="dossier-list"),

    # Cyber terminal
    path("api/comms/cyber/eligible/", cyber_views.cyber_eligible, name="cyber-eligible"),
    path("api/comms/cyber/intercepted/", cyber_views.intercepted_threads, name="intercepted-threads"),
    path("api/comms/threads/<int:thread_id>/cyber/", cyber_views.thread_cyber_status, name="cyber-status"),
    path("api/comms/threads/<int:thread_id>/cyber/roll/", cyber_views.cyber_roll, name="cyber-roll"),
    path("api/comms/threads/<int:thread_id>/cyber/modify/", cyber_views.cyber_modify, name="cyber-modify"),
    path("api/comms/threads/<int:thread_id>/cyber/close/", cyber_views.close_connection, name="cyber-close"),
]
