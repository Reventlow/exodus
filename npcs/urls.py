from django.urls import path
from . import views

urlpatterns = [
    path("npcs/", views.npc_list_page, name="npc_list"),
    path("npcs/<int:pk>/", views.npc_detail_page, name="npc_detail"),
    path("api/npcs/", views.api_npc_list, name="api_npc_list"),
    path("api/npcs/<int:pk>/", views.api_npc_detail, name="api_npc_detail"),
    path("api/npcs/<int:pk>/image/", views.api_npc_image, name="api_npc_image"),
]
