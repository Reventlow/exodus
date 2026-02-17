from django.urls import path
from . import views

urlpatterns = [
    path("", views.character_list_page, name="character_list"),
    path("character/<int:pk>/", views.character_sheet_page, name="character_sheet"),
    path("api/characters/", views.api_character_list, name="api_character_list"),
    path("api/characters/<int:pk>/", views.api_character_detail, name="api_character_detail"),
]
