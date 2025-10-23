from django.urls import path

from . import views

app_name = "announcements"

urlpatterns = [
    path("", views.feed, name="feed"),
    path("watchlists/", views.watchlist_index, name="watchlist-index"),
    path("watchlists/create/", views.watchlist_create, name="watchlist-create"),
    path("watchlists/<int:pk>/", views.watchlist_detail, name="watchlist-detail"),
    path("watchlists/<int:pk>/rename/", views.watchlist_rename, name="watchlist-rename"),
    path("watchlists/<int:pk>/delete/", views.watchlist_delete, name="watchlist-delete"),
    path(
        "watchlists/<int:pk>/remove-company/<int:company_id>/",
        views.watchlist_remove_company,
        name="watchlist-remove-company",
    ),
    path("preferences/", views.preferences, name="preferences"),
]
