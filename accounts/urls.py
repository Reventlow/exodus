from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("register/", views.register_view, name="register"),
    path("profile/", views.profile_view, name="profile"),
    path("api/admin/set-last-activity/", views.api_admin_set_last_activity,
         name="api-admin-set-last-activity"),
    path("api/admin/users/", views.api_admin_list_user_profiles,
         name="api-admin-list-users"),
    path("api/admin/users/<str:username>/", views.api_admin_get_user_profile,
         name="api-admin-get-user"),
    path("api/admin/users/<str:username>/set-active/",
         views.api_admin_set_user_active, name="api-admin-set-user-active"),
]
